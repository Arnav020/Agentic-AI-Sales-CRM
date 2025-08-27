import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from ollama import chat
import json
import re


class EnrichmentAgent:
    def __init__(self, model="mistral:latest"):
        self.model = model
        # Expanded industry keywords for multiple sectors
        self.industry_terms = [
            # Food & Beverage
            "cafe", "tea", "coffee", "snack", "food", "beverage", "retail",
            "restaurant", "franchise", "hospitality", "bakery", "fast food",
            "dining", "outlet", "chain",

            # Technology
            "software", "it services", "information technology", "technology",
            "saas", "cloud", "artificial intelligence", "ai", "machine learning",
            "data", "cybersecurity", "consulting", "automation", "blockchain", "iot",

            # Finance
            "banking", "fintech", "insurance", "lending", "investment", "trading",
            "mutual fund", "capital market", "wealth management", "payment gateway",

            # Healthcare
            "hospital", "clinic", "pharma", "pharmaceutical", "biotech",
            "diagnostics", "healthcare", "telemedicine", "medical devices", "wellness",

            # Manufacturing & Energy
            "manufacturing", "factory", "automobile", "electronics", "engineering",
            "renewable", "solar", "oil", "gas", "energy", "power plant",

            # Education
            "edtech", "education", "university", "school", "training",
            "elearning", "coaching"
        ]

    # -----------------------------
    # Scrape About Page
    # -----------------------------
    def scrape_about(self, website):
        about_paths = ["/pages/about-brand", "/about", "/about-us", "/"]
        description = ""
        for path in about_paths:
            try:
                url = website.rstrip("/") + path
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    main_content = soup.find("main") or soup.find("section")
                    if main_content:
                        description = main_content.get_text(" ", strip=True)[:800]
                    else:
                        meta = soup.find("meta", attrs={"name": "description"})
                        description = meta["content"] if meta and meta.get("content") else soup.get_text(" ", strip=True)[:800]
                    break
            except:
                continue
        return description or "No description available"

    # -----------------------------
    # Detect Hiring
    # -----------------------------
    def detect_hiring(self, website):
        try:
            r = requests.get(website, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            links = [a['href'] for a in soup.find_all("a", href=True)
                     if any(word in a.get_text().lower() for word in ["career", "job", "join", "hiring"])]

            for link in links:
                if not link.startswith("http"):
                    link = website.rstrip("/") + "/" + link.lstrip("/")
                try:
                    r2 = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    text = r2.text.lower()
                    if "forms.gle" in text or "docs.google.com/forms" in text:
                        return True
                    if any(word in text for word in ["apply", "position", "opening", "job", "vacancy"]):
                        return True
                except:
                    continue
        except:
            pass
        return False

    # -----------------------------
    # DuckDuckGo Signals
    # -----------------------------
    def duckduckgo_signals(self, company_name):
        signals = {"funding_signal": 0.0, "expansion_signal": 0.0, "negative_signal": 0.0}
        queries = {
            "funding_signal": f"{company_name} funding investment venture capital news",
            "expansion_signal": f"{company_name} expansion opening new outlets branches stores launch",
            "negative_signal": f"{company_name} layoffs shutdown bankruptcy closure insolvency"
        }

        keywords = {
            "funding_signal": ["raised", "funding", "series", "venture capital", "secured investment"],
            "expansion_signal": ["opening", "expanding", "launched", "new outlet", "store launch", "new branch"],
            "negative_signal": ["shutdown", "bankruptcy", "layoffs", "closure", "insolvency", "winding up"]
        }

        try:
            with DDGS() as ddgs:
                for key, query in queries.items():
                    results = list(ddgs.text(query, max_results=5))
                    score = 0
                    for r in results:
                        snippet = (r.get("body") or "").lower()
                        for kw in keywords[key]:
                            if kw in snippet:
                                score += 0.3 if key != "negative_signal" else 0.5
                    signals[key] = min(1.0, round(score, 2))
        except Exception as e:
            print("DuckDuckGo error:", e)

        # Calibration
        if signals["expansion_signal"] >= 0.5 or signals["funding_signal"] >= 0.5:
            signals["negative_signal"] = min(signals["negative_signal"], 0.2)

        return signals

    # -----------------------------
    # Structured Info (patched schema with safe fallback)
    # -----------------------------
    def extract_structured_info(self, snippets, company_name):
        snippets_text = " ".join(snippets)[:1200]
        messages = [
            {
                "role": "system",
                "content": """You are a company info extractor.
                Return ONLY valid JSON in this schema:
                {
                  "name": string,
                  "founded_year": string,
                  "employees_count": string,
                  "headquarters": string,
                  "industry": string,
                  "description": string
                }
                Never return null. Use "Unknown" if info not found.
                Description must summarize the company’s products/services/market.
                """
            },
            {
                "role": "user",
                "content": f"Extract structured info about {company_name} from this text:\n{snippets_text}"
            }
        ]
        try:
            response = chat(model=self.model, messages=messages)
            content = response['message']['content'].strip()
            if content.startswith("```"):
                content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()

            info = json.loads(content)
        except Exception as e:
            print("Ollama chat error:", e)
            info = {}

        return {
            "name": info.get("name") or company_name,
            "founded_year": info.get("founded_year") or "Unknown",
            "employees_count": info.get("employees_count") or "Unknown",
            "headquarters": info.get("headquarters") or "Unknown",
            "industry": info.get("industry") or "Unknown",
            "description": info.get("description") or f"{company_name} is a company with growing market presence."
        }

    # -----------------------------
    # Main enrichment
    # -----------------------------
    def enrich_lead(self, company_name, website):
        enrichment = {
            "company": company_name,
            "website": website,
            "description": self.scrape_about(website),
            "hiring": self.detect_hiring(website),
            "industry_keywords": [],
        }

        desc_lower = enrichment["description"].lower()
        keywords_found = []
        for kw in self.industry_terms:
            if kw in desc_lower:
                if kw in ["ai", "artificial intelligence", "machine learning", "blockchain", "iot"]:
                    if any(t in desc_lower for t in ["software", "platform", "saas", "technology"]):
                        keywords_found.append(kw)
                else:
                    keywords_found.append(kw)

        enrichment["industry_keywords"] = list(set(keywords_found))

        enrichment.update(self.duckduckgo_signals(company_name))

        ddg_snippets = []
        queries = ["company size", "founded", "headquarters", "industry"]
        try:
            with DDGS() as ddgs:
                for q in queries:
                    query = f"{company_name} {q}"
                    results = list(ddgs.text(query, max_results=3))
                    for r in results:
                        ddg_snippets.append(r.get("body") or "")
        except Exception as e:
            print("DuckDuckGo error:", e)

        ollama_info = self.extract_structured_info(ddg_snippets, company_name)
        enrichment["structured_info"] = ollama_info

        return enrichment


# -----------------------------
# Run Example
# -----------------------------
if __name__ == "__main__":
    agent = EnrichmentAgent(model="mistral:latest")
    company = "Chaayos"
    website = "https://chaayos.com"
    enriched_data = agent.enrich_lead(company, website)

    print(json.dumps(enriched_data, indent=2))
