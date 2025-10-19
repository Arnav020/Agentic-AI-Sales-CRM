# agents/enrichment_agent.py
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
import json, re, os, time, ast, threading, logging, queue, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# -----------------------------
# Setup Logging
# -----------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/enrichment_agent.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# -----------------------------
# Ollama / Mistral Setup
# -----------------------------
USE_OLLAMA = True
OLLAMA_MODEL = "mistral:latest"

if USE_OLLAMA:
    try:
        from ollama import chat
        ollama_client = True
        logging.info("Ollama Mistral client ready")
    except Exception as e:
        ollama_client = False
        logging.warning(f"Ollama setup failed: {e}")
else:
    ollama_client = False
    logging.info("USE_OLLAMA=False. No LLM will be used")

# -----------------------------
# Configuration
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
    s = company.get("structured_info", {})
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
    def __init__(self, model=OLLAMA_MODEL):
        self.model = model
        self.city_regex = re.compile(
            r"\b(New Delhi|Delhi|Gurugram|Bangalore|Mumbai|Pune|Hyderabad|Chennai|Kolkata|Noida|"
            r"Ahmedabad|Jaipur|Lucknow|Singapore|London|San Francisco|New York|Toronto|Sydney|Dubai|Paris|Berlin|Tokyo|Seoul)\b",
            re.I
        )

    def safe_mistral_generate(self, prompt, max_tokens=1024):
        if not ollama_client:
            return prompt[:500]
        for attempt in range(MAX_RETRIES):
            try:
                response = chat(
                    model=self.model,
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
# Runner
# -----------------------------
if __name__ == "__main__":
    agent = EnrichmentAgent()
    with open("inputs/companies.json", "r", encoding="utf-8") as f:
        companies = json.load(f)

    raw_results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(agent.enrich_lead_prefetch, c["name"], c["website"]): c for c in companies}
        for future in as_completed(futures):
            c = futures[future]
            try:
                result = future.result()
                raw_results.append(result)
                logging.info(f"✅ Prefetched: {c['name']}")
            except Exception as e:
                logging.error(f"❌ Prefetch failed for {c['name']}: {e}")

    final_results = []
    for r in sorted(raw_results, key=lambda x: x["company"]):
        try:
            info = agent.extract_structured_info(r["company"], r["description"], r["snippets"])
            r["structured_info"] = info
            del r["snippets"]
            final_results.append(clean_company_record(r))  # <-- safe cleaning step
            logging.info(f"✅ LLM enriched & cleaned: {r['company']}")
        except Exception as e:
            logging.error(f"❌ LLM enrich failed for {r['company']}: {e}")

    os.makedirs("outputs", exist_ok=True)
    with open("outputs/enriched_companies.json", "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=2, ensure_ascii=False)

    print(f"✅ Done. Cleaned and saved {len(final_results)} companies.")
