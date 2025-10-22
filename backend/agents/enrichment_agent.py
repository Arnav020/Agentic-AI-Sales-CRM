# backend/agents/enrichment_agent.py
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
import json
import re
import os
import time
import ast
import logging
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from backend.db.mongo import save_user_output

# -----------------------------
# Configuration (unchanged behaviour)
# -----------------------------
MAX_WORKERS = 5
HTTP_TIMEOUT = 10
MAX_RETRIES = 3
SLEEP_BASE = 1.5  # exponential backoff base delay (seconds)

# -----------------------------
# Utility: Safe Text Normalization
# -----------------------------
def normalize_text(value):
    if not value:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if v)
    return re.sub(r"\s+", " ", str(value)).strip()

# -----------------------------
# Cleaning Function for Final Output
# -----------------------------
def clean_company_record(company):
    # Signals normalization
    for key in ["funding_signal", "expansion_signal", "negative_signal"]:
        try:
            val = float(company.get(key, 0))
            company[key] = min(max(val, 0.0), 1.0)
        except Exception:
            company[key] = 0.0

    # Ensure hiring field is boolean
    company["hiring"] = bool(company.get("hiring", False))

    # Normalize top-level strings
    company["company"] = normalize_text(company.get("company"))
    company["website"] = normalize_text(company.get("website"))
    company["description"] = normalize_text(company.get("description"))

    # Handle structured_info fields
    s = company.get("structured_info", {}) or {}
    cleaned = {
        "company_name": normalize_text(s.get("company_name")),
        "founded_year": normalize_text(s.get("founded_year")),
        "employees_count": normalize_text(s.get("employees_count")),
        "headquarters": normalize_text(s.get("headquarters")),
        "industry": normalize_text(s.get("industry")),
        "description": normalize_text(s.get("description")),
        "products": s.get("products", []),
        "services": s.get("services", [])
    }

    # Enforce list type for products/services
    if isinstance(cleaned["products"], str):
        cleaned["products"] = [cleaned["products"]]
    if isinstance(cleaned["services"], str):
        cleaned["services"] = [cleaned["services"]]

    company["structured_info"] = cleaned
    return company

# -----------------------------
# Enrichment Agent
# -----------------------------
class EnrichmentAgent:
    def __init__(self, user_root: str = None, model: str = "mistral:latest", max_workers: int = MAX_WORKERS):
        """
        user_root: Path to the user's folder (e.g. users/user_demo). If None, falls back to backend/ (single-tenant).
        model: Ollama/Mistral model string (keeps existing behavior).
        """
        # define project root (backend/)
        # file is agents/enrichment_agent.py so parents[1] -> backend/
        self.project_root = Path(__file__).resolve().parents[1]

        # Ensure we load the backend .env explicitly so Mongo and other modules get correct env values.
        try:
            load_dotenv(self.project_root / ".env")
        except Exception:
            # fallback to default load_dotenv behavior
            load_dotenv()


        # define user_root
        if user_root:
            self.user_root = Path(user_root)
        else:
            # fallback: use project root for older single-tenant behavior
            self.user_root = self.project_root

        # normalize user_root if it's just a username (like "user_demo")
        # ensure it's a path like backend/users/<user>
        if self.user_root.name and self.user_root.exists() is False and str(self.user_root).startswith("users"):
            # likely passed "users/<user>" relative; make absolute relative to project_root
            self.user_root = (self.project_root / self.user_root)

        # If still pointing to backend/ (single-tenant), that's acceptable.
        # define per-user directories
        self.inputs_dir = (self.user_root / "inputs")
        self.outputs_dir = (self.user_root / "outputs")
        self.logs_dir = (self.user_root / "logs")
        # ensure directories exist
        for d in (self.inputs_dir, self.outputs_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

        # derive a user id for multi-tenant documents (use folder name if present)
        try:
            # If user_root is like backend/users/user_demo -> take user_demo
            if self.user_root.parts and "users" in self.user_root.parts:
                # find index of 'users' and pick next segment as user id
                parts = list(self.user_root.parts)
                if "users" in parts:
                    idx = parts.index("users")
                    if idx + 1 < len(parts):
                        self.user_id = parts[idx + 1]
                    else:
                        self.user_id = "default_user"
                else:
                    self.user_id = self.user_root.name or "default_user"
            else:
                self.user_id = self.user_root.name or "default_user"
        except Exception:
            self.user_id = "default_user"

        # logging per-user
        self.log_file = self.logs_dir / "enrichment_agent.log"
        self._setup_logging()

        # model and concurrency
        self.model = model
        self.MAX_WORKERS = max_workers

        # city regex (same as before)
        self.city_regex = re.compile(
            r"\b(New Delhi|Delhi|Gurugram|Bangalore|Mumbai|Pune|Hyderabad|Chennai|Kolkata|Noida|"
            r"Ahmedabad|Jaipur|Lucknow|Singapore|London|San Francisco|New York|Toronto|Sydney|Dubai|Paris|Berlin|Tokyo|Seoul)\b",
            re.I
        )

        # Ollama / Mistral setup from original script
        self.USE_OLLAMA = True
        self.OLLAMA_MODEL = model
        if self.USE_OLLAMA:
            try:
                from ollama import chat  # local import; may fail if not installed
                self.ollama_client = True
                logging.info("Ollama Mistral client ready")
            except Exception as e:
                self.ollama_client = False
                logging.warning(f"Ollama setup failed: {e}")
        else:
            self.ollama_client = False
            logging.info("USE_OLLAMA=False. No LLM will be used")

    def _setup_logging(self):
        # configure logging to write to the per-user log file
        # keep simple basicConfig to avoid interfering with other modules
        logging.getLogger().handlers = []  # clear existing handlers to avoid duplicates
        logging.basicConfig(
            filename=str(self.log_file),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s"
        )
        # also log to console for interactive debugging
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        console.setFormatter(formatter)
        logging.getLogger().addHandler(console)
        logging.info(f"EnrichmentAgent logging initialized. Logs -> {self.log_file}")

    # -----------------------------
    # LLM / Ollama helper (unchanged)
    # -----------------------------
    def safe_mistral_generate(self, prompt, max_tokens=1024):
        if not getattr(self, "ollama_client", False):
            return prompt[:500]
        for attempt in range(MAX_RETRIES):
            try:
                # local import to avoid module-level crash if ollama not installed
                from ollama import chat
                response = chat(
                    model=self.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0, "top_p": 1}
                )
                content = getattr(getattr(response, "message", None), "content", None) or response.get("content", "")
                if content:
                    return str(content).strip()
            except Exception as e:
                logging.warning(f"Mistral call failed (attempt {attempt+1}): {e}")
                time.sleep(SLEEP_BASE * (2 ** attempt))
        return ""

    # -----------------------------
    # Network request helper (unchanged)
    # -----------------------------
    def safe_request(self, url):
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=HTTP_TIMEOUT)
                if r.status_code == 200:
                    return r
            except Exception as e:
                logging.warning(f"Request failed for {url} (attempt {attempt+1}): {e}")
                time.sleep(SLEEP_BASE * (2 ** attempt))
        return None

    def scrape_about(self, website):
        try:
            r = self.safe_request(website)
            if not r:
                return "No description available"
            soup = BeautifulSoup(r.text, "html.parser")

            ld_json = soup.find("script", type="application/ld+json")
            if ld_json and ld_json.string:
                try:
                    data = json.loads(ld_json.string)
                    if isinstance(data, dict) and data.get("description"):
                        return data["description"][:800]
                except Exception:
                    pass

            meta = (soup.find("meta", attrs={"property": "og:description"}) or
                    soup.find("meta", attrs={"name": "description"}))
            if meta and meta.get("content"):
                return meta["content"][:800]

            main_content = soup.find("main") or soup.find("section")
            if main_content:
                return main_content.get_text(" ", strip=True)[:800]

            return soup.get_text(" ", strip=True)[:800]
        except Exception as e:
            logging.error(f"[scrape_about] {website}: {e}")
            return "No description available"

    def _throttled_ddg_text(self, query, max_results=3):
        try:
            time.sleep(0.5 + random.random())
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as e:
            logging.warning(f"[DDGS] query failed: {query[:40]}... ({e})")
            return []

    # -----------------------------
    # Heuristics (unchanged)
    # -----------------------------
    def detect_hiring(self, company_name, website):
        try:
            r = self.safe_request(website)
            if r and any(word in r.text.lower() for word in ["career", "careers", "jobs", "hiring", "join us"]):
                return True
        except Exception:
            pass
        results = self._throttled_ddg_text(f"{company_name} hiring jobs openings careers", 5)
        for r in results:
            if any(kw in (r.get("body", "").lower()) for kw in ["hiring", "recruiting", "join our team"]):
                return True
        return False

    def duckduckgo_signals(self, company_name):
        signals = {"funding_signal": 0.0, "expansion_signal": 0.0, "negative_signal": 0.0}
        queries = {
            "funding_signal": f"{company_name} funding investment venture capital news",
            "expansion_signal": f"{company_name} expansion launch new office store opening",
            "negative_signal": f"{company_name} layoffs shutdown bankruptcy closure scandal"
        }
        keywords = {
            "funding_signal": ["raised", "funding", "series", "investment"],
            "expansion_signal": ["opening", "expanding", "launched", "new office"],
            "negative_signal": ["shutdown", "bankruptcy", "layoffs", "closure", "scandal"]
        }
        for key, query in queries.items():
            results = self._throttled_ddg_text(query, 5)
            score = sum(any(kw in (r.get("body", "").lower()) for kw in keywords[key]) for r in results)
            signals[key] = min(1.0, round(score * 0.25, 2))
        if signals["expansion_signal"] >= 0.5 or signals["funding_signal"] >= 0.5:
            signals["negative_signal"] = min(signals["negative_signal"], 0.2)
        return signals

    def collect_snippets(self, company_name):
        snippets, queries = [], ["company size", "founded", "headquarters", "industry profile", "about us"]
        for q in queries:
            results = self._throttled_ddg_text(f"{company_name} {q}", 3)
            snippets.extend([r.get("body", "") for r in results if r.get("body")])
        filtered = [b for b in snippets if not any(ex in b.lower()
                    for ex in ["linkedin", "glassdoor", "indeed", "facebook", "twitter", "crunchbase", "youtube"])]
        return " ".join(filtered)[:2500]

    # -----------------------------
    # JSON parsing helper (unchanged)
    # -----------------------------
    def _robust_parse_json(self, raw_text):
        if not raw_text:
            raise ValueError("No raw_text provided")
        s = re.sub(r"^```(?:json)?\s*|```$", "", raw_text.strip(), flags=re.I | re.M)
        s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
        s = re.sub(r",\s*([}\]])", r"\1", s)
        first, last = s.find("{"), s.rfind("}")
        s_inner = s[first:last + 1] if first != -1 and last > first else s
        try:
            return json.loads(s_inner)
        except Exception:
            return ast.literal_eval(s_inner)

    def extract_structured_info(self, company_name, description, snippets):
        schema = {
            "company_name": company_name,
            "founded_year": "Unknown",
            "employees_count": "Unknown",
            "headquarters": "Unknown",
            "industry": "Unknown",
            "description": (description or "")[:500],
            "products": [],
            "services": []
        }
        summary_prompt = (
            f"Summarize info about {company_name} (industry, HQ, employees, products, services):\n\n"
            f"DESCRIPTION:\n{description}\n\nSNIPPETS:\n{snippets}"
        )
        summary = self.safe_mistral_generate(summary_prompt)
        extract_prompt = (
            f"Extract factual JSON: company_name, founded_year, employees_count, headquarters, "
            f"industry, description, products, services from this:\n\n{summary}\n\nReturn only JSON."
        )
        for attempt in range(MAX_RETRIES):
            try:
                raw = self.safe_mistral_generate(extract_prompt)
                parsed = self._robust_parse_json(raw)
                return {**schema, **parsed}
            except Exception as e:
                logging.warning(f"[extract_structured_info] Parse failed for {company_name} (attempt {attempt+1}): {e}")
                time.sleep(SLEEP_BASE * (2 ** attempt))
        return schema

    def enrich_lead_prefetch(self, company_name, website):
        desc = self.scrape_about(website)
        snippets = self.collect_snippets(company_name)
        signals = self.duckduckgo_signals(company_name)
        hiring = self.detect_hiring(company_name, website)
        return {
            "company": company_name,
            "website": website,
            "description": desc,
            "hiring": hiring,
            **signals,
            "snippets": snippets
        }

    # -----------------------------
    # Persistence helper (Mongo + JSON backup)
    # -----------------------------
    def _persist_final_results(self, final_results: list, correlation_id: str):
        """
        Persist final_results (list of cleaned company records) to MongoDB and write JSON backups.
        Each run is inserted as a single document into 'enriched_companies' with metadata.
        """
        timestamp = datetime.utcnow().isoformat()
        doc = {
            "user_id": self.user_id,
            "correlation_id": correlation_id,
            "created_at": timestamp,
            "count": len(final_results),
            "results": final_results
        }


        # Always write a timestamped backup file in the user's outputs directory
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = self.outputs_dir / f"enriched_companies_{ts}.json"
        try:
            with backup_file.open("w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False, default=str)
            logging.info(f"Wrote JSON backup to {backup_file}")
        except Exception as e:
            logging.exception(f"Failed to write backup JSON to {backup_file}: {e}")

        # Also keep the canonical filename for downstream consumers (overwrites)
        canonical_file = self.outputs_dir / "enriched_companies.json"
        try:
            with canonical_file.open("w", encoding="utf-8") as f:
                json.dump(final_results, f, indent=2, ensure_ascii=False, default=str)
            logging.info(f"Wrote canonical output to {canonical_file}")
        except Exception as e:
            logging.exception(f"Failed to write canonical output to {canonical_file}: {e}")

    # -----------------------------
    # High-level run method (keeps original behaviour)
    # -----------------------------
    def run(self):
        """
        Run the full enrichment pipeline using inputs/enrichment list from the user's inputs directory.
        Writes results to user's outputs directory and logs to the user's logs directory.
        """
        inputs_file = self.inputs_dir / "companies.json"
        if not inputs_file.exists():
            logging.error(f"Inputs file not found: {inputs_file}")
            return

        try:
            with inputs_file.open("r", encoding="utf-8") as f:
                companies = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load companies from {inputs_file}: {e}")
            return

        raw_results = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {executor.submit(self.enrich_lead_prefetch, c.get("name"), c.get("website")): c for c in companies}
            for future in as_completed(futures):
                c = futures[future]
                try:
                    result = future.result()
                    raw_results.append(result)
                    logging.info(f"✅ Prefetched: {c.get('name')}")
                except Exception as e:
                    logging.error(f"❌ Prefetch failed for {c.get('name')}: {e}")

        final_results = []
        for r in sorted(raw_results, key=lambda x: x.get("company", "")):
            try:
                info = self.extract_structured_info(r.get("company"), r.get("description"), r.get("snippets"))
                r["structured_info"] = info
                r.pop("snippets", None)
                final_results.append(clean_company_record(r))  # <-- safe cleaning step
                logging.info(f"✅ LLM enriched & cleaned: {r.get('company')}")
            except Exception as e:
                logging.error(f"❌ LLM enrich failed for {r.get('company')}: {e}")

        # generate correlation id for this run
        correlation_id = str(uuid.uuid4())

        # Persist results (Mongo + JSON backup) via helper
        try:
            self._persist_final_results(final_results, correlation_id)
            logging.info(f"✅ Done. Cleaned and saved {len(final_results)} companies (correlation_id={correlation_id})")
        except Exception as e:
            logging.exception(f"Unexpected error while persisting results: {e}")

        # inside run(), after writing out_file and logging:
        try:
            # store full results per user
            user_id = self.user_root.name if self.user_root else "unknown"
            save_user_output(user_id=user_id, agent="enrichment_agent", output_type="enriched_companies", data={"results": final_results})
            logging.info("Saved enriched_companies to user_outputs (mongo)")
        except Exception as e:
            logging.exception(f"Failed to save enriched companies to user_outputs: {e}")

# -----------------------------
# Runner / Entrypoint for both Orchestrator and Standalone use
# -----------------------------
def main(user_folder: str | None = None):
    """
    Main entrypoint for enrichment_agent.
    Used both by:
      • The orchestrator (via import + main())
      • Standalone command line runs
    """
    # Determine user path
    if user_folder:
        user_path = Path(user_folder)
    else:
        # if called standalone and no env variable provided
        env_user = os.getenv("USER_FOLDER")
        user_path = Path(env_user) if env_user else None

    # Initialize and run
    agent = EnrichmentAgent(user_root=user_path)
    agent.run()


if __name__ == "__main__":
    import sys
    # Allow standalone run: python agents/enrichment_agent.py [user_name]
    user_arg = sys.argv[1] if len(sys.argv) >= 2 else None
    if user_arg:
        # Build full path like users/<user_arg> relative to backend/
        user_folder = str(Path("users") / user_arg)
    else:
        user_folder = None

    main(user_folder)
