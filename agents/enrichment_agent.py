# agents/enrichment_agent.py
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from ollama import chat
import json
import re
import os
import time
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed

class EnrichmentAgent:
    def __init__(self, model="mistral:latest"):
        self.model = model
        self.city_regex = re.compile(
            r"\b(New Delhi|Delhi|Gurugram|Bangalore|Bengaluru|Mumbai|Pune|Hyderabad|Chennai|Kolkata|Noida|Ahmedabad)\b",
            re.I
        )

    # -----------------------------
    # Scrape About / Meta / JSON-LD
    # -----------------------------
    def scrape_about(self, website):
        try:
            r = requests.get(website, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            # JSON-LD (company schema)
            ld_json = soup.find("script", type="application/ld+json")
            if ld_json and ld_json.string:
                try:
                    data = json.loads(ld_json.string)
                    if isinstance(data, dict) and data.get("description"):
                        return data.get("description")[:800]
                except:
                    # ignore parse errors for JSON-LD
                    pass

            # Meta description (og:description or name=description)
            meta = (soup.find("meta", attrs={"property": "og:description"}) or
                    soup.find("meta", attrs={"name": "description"}))
            if meta and meta.get("content"):
                return meta["content"][:800]

            # Visible content
            main_content = soup.find("main") or soup.find("section")
            if main_content:
                return main_content.get_text(" ", strip=True)[:800]

            # Fallback to whole page text
            return soup.get_text(" ", strip=True)[:800]
        except Exception as e:
            print(f"[scrape_about] Scrape failed for {website}: {e}")
            return "No description available"

    # -----------------------------
    # Hiring Detection
    # -----------------------------
    def detect_hiring(self, website):
        try:
            r = requests.get(website, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            txt = r.text.lower()
            if any(word in txt for word in ["career", "careers", "job", "jobs", "hiring", "join us", "we're hiring"]):
                return True
            # some career pages are on third-party ATS; check page for common ATS domains
            if any(domain in txt for domain in ["greenhouse.io", "lever.co", "workday.com", "smartrecruiters.com"]):
                return True
        except Exception:
            pass
        return False

    # -----------------------------
    # DuckDuckGo Signals
    # -----------------------------
    def duckduckgo_signals(self, company_name):
        signals = {"funding_signal": 0.0, "expansion_signal": 0.0, "negative_signal": 0.0}
        queries = {
            "funding_signal": f"{company_name} funding investment venture capital news",
            "expansion_signal": f"{company_name} expansion launch new office store opening",
            "negative_signal": f"{company_name} layoffs shutdown bankruptcy closure scandal"
        }
        keywords = {
            "funding_signal": ["raised", "funding", "series", "venture capital", "investment"],
            "expansion_signal": ["opening", "expanding", "launched", "new office", "store launch", "expansion"],
            "negative_signal": ["shutdown", "bankruptcy", "layoffs", "closure", "fraud", "scandal"]
        }

        try:
            with DDGS() as ddgs:
                for key, query in queries.items():
                    try:
                        results = list(ddgs.text(query, max_results=6))
                        # compute a capped score (prevent repeats inflating it)
                        score = 0.0
                        seen_snips = set()
                        for r in results:
                            body = (r.get("body") or "").lower()
                            if not body or body in seen_snips:
                                continue
                            seen_snips.add(body)
                            for kw in keywords[key]:
                                if kw in body:
                                    score += 0.33 if key != "negative_signal" else 0.5
                        signals[key] = min(1.0, round(score, 2))
                    except Exception as e:
                        # don't stop if a single query fails
                        print(f"[duckduckgo_signals] query error for {company_name} ({key}): {e}")
        except Exception as e:
            print(f"[duckduckgo_signals] DDGS init failed for {company_name}: {e}")

        # Simple calibration: strong funding or expansion reduces weight of negative signal
        if signals["expansion_signal"] >= 0.5 or signals["funding_signal"] >= 0.5:
            signals["negative_signal"] = min(signals["negative_signal"], 0.2)

        return signals

    # -----------------------------
    # Collect DDG Snippets (parallel)
    # -----------------------------
    def collect_snippets(self, company_name):
        snippets = []
        queries = ["company size", "founded", "headquarters", "industry profile", "about us"]
        try:
            with DDGS() as ddgs, ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(ddgs.text, f"{company_name} {q}", 3) for q in queries]
                for future in as_completed(futures):
                    try:
                        results = list(future.result())
                        for r in results:
                            b = r.get("body") or ""
                            if b:
                                snippets.append(b)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[collect_snippets] DDGS error for {company_name}: {e}")
        return snippets

    # -----------------------------
    # Robust JSON parsing utility
    # -----------------------------
    def _robust_parse_json(self, raw_text):
        """
        Try multiple strategies to parse LLM output into a Python dict:
        1) strip code fences, extract first {...} block, try json.loads
        2) ast.literal_eval (accepts single quotes / Python dicts)
        3) attempt to quote unquoted keys and replace single->double quotes then json.loads
        If all fail, raise ValueError with debug info.
        """
        if raw_text is None:
            raise ValueError("No raw_text provided")

        s = raw_text.strip()

        # 1) remove fenced code blocks (```json ... ``` or ``` ...)
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I | re.M)
        s = re.sub(r"```$", "", s, flags=re.I | re.M)
        # 2) trim to first {...} ... last } if they exist (helps when assistant adds explanation)
        first = s.find("{")
        last = s.rfind("}")
        if first != -1 and last != -1 and last > first:
            s_inner = s[first:last + 1]
        else:
            s_inner = s

        # Try json.loads directly
        try:
            return json.loads(s_inner)
        except Exception as e_json:
            # Try ast.literal_eval to accept single quotes / python-style dict
            try:
                parsed = ast.literal_eval(s_inner)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as e_ast:
                # Try to transform unquoted keys to quoted keys
                try:
                    # add quotes around unquoted keys like: {company_name: "X"} -> {"company_name": "X"}
                    s_keys = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_-]*)\s*:', r'\1"\2":', s_inner)
                    # replace single quotes delimiting strings -> double quotes
                    s_quotes = s_keys.replace("'", '"')
                    return json.loads(s_quotes)
                except Exception as e_try:
                    # Give a helpful exception with examples of why parsing failed
                    short = s_inner[:1000].replace("\n", " ")
                    raise ValueError(f"Failed JSON parse. json_err={e_json}; ast_err={e_ast}; fix_err={e_try}; raw_preview={short}")

    # -----------------------------
    # Ollama Extraction with Schema Enforcement
    # -----------------------------
    def extract_structured_info(self, company_name, description, snippets, retries=2):
        """
        Ask the model to produce a strict JSON with the fixed schema.
        Attempt parsing robustly and retry if needed.
        Returns a dict with stable keys.
        """

        # fixed output schema (defaults used as fallback)
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

        # build context
        snippets_text = " ".join(snippets)[:2000]
        context = f"DESCRIPTION:\n{(description or '')}\n\nSNIPPETS:\n{snippets_text}"

        # strict prompt instructing double quotes and exact keys
        prompt = (
            "You are a company information extractor. RETURN ONLY a single JSON object and NOTHING else. "
            "The JSON MUST use double quotes for keys and string values, and must contain exactly the following keys:\n"
            '["company_name","founded_year","employees_count","headquarters","industry","description","products","services"]\n'
            "Each field should be a string, except products and services which should be arrays of strings. "
            "If a value is not available, use the string \"Unknown\" (for strings) or an empty array (for lists). "
            "Do NOT add commentary, explanation, or extra fields. Do NOT wrap the JSON in markdown fences."
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Extract the JSON for {company_name} from the following context:\n\n{context}"}
        ]

        last_err = None
        for attempt in range(retries + 1):
            try:
                response = chat(model=self.model, messages=messages, options={"temperature": 0, "top_p": 1})
                raw = response.get("message", {}).get("content")
                if raw is None:
                    raw = response.get("content") or ""
                raw = (raw or "").strip()

                # Try robust parse
                parsed = self._robust_parse_json(raw)

                # Normalize keys: lower-case and ensure exact schema keys
                normalized = {}
                for k in schema.keys():
                    if k in parsed:
                        normalized[k] = parsed[k]
                    else:
                        # try variants (like "Company Name", "companyName", etc.)
                        for pkey in parsed.keys():
                            lk = str(pkey).lower().replace(" ", "_")
                            if lk == k:
                                normalized[k] = parsed[pkey]
                                break
                        else:
                            normalized[k] = schema[k]  # fallback

                # Post-process types: ensure lists for products/services and strings for others
                if not isinstance(normalized.get("products"), list):
                    normalized["products"] = normalized["products"] if normalized["products"] is not None else []
                    if not isinstance(normalized["products"], list):
                        normalized["products"] = [str(normalized["products"])] if normalized["products"] != "Unknown" else []
                if not isinstance(normalized.get("services"), list):
                    normalized["services"] = normalized["services"] if normalized["services"] is not None else []
                    if not isinstance(normalized["services"], list):
                        normalized["services"] = [str(normalized["services"])] if normalized["services"] != "Unknown" else []

                # Convert non-string simple fields to strings (for uniformity)
                for k in ["company_name", "founded_year", "employees_count", "headquarters", "industry", "description"]:
                    v = normalized.get(k, "Unknown")
                    if v is None:
                        normalized[k] = "Unknown"
                    elif isinstance(v, (list, dict)):
                        normalized[k] = json.dumps(v)
                    else:
                        normalized[k] = str(v)

                return normalized

            except Exception as e:
                last_err = e
                preview = ""
                try:
                    preview = raw[:1000].replace("\n", " ")
                except:
                    preview = "<no preview>"
                print(f"[extract_structured_info] parse attempt {attempt+1} failed for {company_name}: {e}. raw_preview={preview}")
                if attempt < retries:
                    time.sleep(1)  # small backoff and retry
                    continue
                else:
                    print(f"[extract_structured_info] All retries failed for {company_name}. Returning fallback schema.")
                    return schema

    # -----------------------------
    # Main enrichment
    # -----------------------------
    def enrich_lead(self, company_name, website):
        description = self.scrape_about(website)
        snippets = self.collect_snippets(company_name)
        signals = self.duckduckgo_signals(company_name)
        info = self.extract_structured_info(company_name, description, snippets)

        return {
            "company": company_name,
            "website": website,
            "description": description,
            "hiring": self.detect_hiring(website),
            "funding_signal": signals["funding_signal"],
            "expansion_signal": signals["expansion_signal"],
            "negative_signal": signals["negative_signal"],
            "structured_info": info
        }


# -----------------------------
# Run Multiple Companies
# -----------------------------
if __name__ == "__main__":
    agent = EnrichmentAgent(model="mistral:latest")

    with open("inputs/companies.json", "r", encoding="utf-8") as f:
        companies = json.load(f)

    enriched = []
    for comp in companies:
        print(f"Enriching: {comp['name']}")
        enriched.append(agent.enrich_lead(comp["name"], comp["website"]))
        time.sleep(1)   # polite pacing between companies

    os.makedirs("outputs", exist_ok=True)
    with open("outputs/enriched_companies.json", "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print("✅ Done. Results saved to outputs/enriched_companies.json")
