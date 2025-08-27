import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from ollama import chat
import json
import re


class EnrichmentAgent:
    def __init__(self, model="mistral:latest"):
        self.model = model

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
                        description = main_content.get_text(" ", strip=True)[:500]
                    else:
                        meta = soup.find("meta", attrs={"name": "description"})
                        description = meta["content"] if meta and meta.get("content") else soup.get_text(" ", strip=True)[:500]
                    break
            except:
                continue
        return description

    # -----------------------------
    # Detect Hiring (crawl all links)
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
    # DuckDuckGo Signals with confidence
    # -----------------------------
    def duckduckgo_signals(self, company_name):
        signals = {"funding_signal": 0.0, "expansion_signal": 0.0, "negative_signal": 0.0}
        queries = {
            "funding_signal": f"{company_name} funding news",
            "expansion_signal": f"{company_name} expansion opening new outlets",
            "negative_signal": f"{company_name} layoffs shutdown bankruptcy"
        }

        try:
            with DDGS() as ddgs:
                for key, query in queries.items():
                    results = list(ddgs.text(query, max_results=5))
                    score = 0
                    for r in results:
                        snippet = (r.get("body") or "").lower()
                        if key == "funding_signal" and any(x in snippet for x in ["raised", "funding", "series"]):
                            score += 0.4
                        if key == "expansion_signal" and any(x in snippet for x in ["opening", "expanding", "launched"]):
                            score += 0.4
                        if key == "negative_signal":
                            if any(x in snippet for x in ["permanent shutdown", "filed for bankruptcy", "mass layoffs", "insolvency"]):
                                if company_name.lower() in snippet:
                                    score += 0.5
                    signals[key] = min(1.0, score) 
        except Exception as e:
            print("DuckDuckGo error:", e)
        return signals

    # -----------------------------
    # Parse About Page for Structured Info (Fallback)
    # -----------------------------
    def parse_about_structured(self, description):
        info = {}
        founded = re.search(r"founded in (\d{4})", description, re.I)
        if founded:
            info["founded_year"] = founded.group(1)
        size = re.search(r"with (\d+) employees", description, re.I)
        if size:
            info["company_size"] = size.group(1)
        return info

    # -----------------------------
    # Structured Info via Ollama Chat
    # -----------------------------
    def extract_structured_info(self, snippets, company_name):
        snippets_text = " ".join(snippets)[:800] 
        messages = [
            {
                "role": "system",
                "content": """You are a strict company info extractor. 
                Return ONLY valid JSON. 
                No extra text, no comments, no markdown, no explanations. 
                Schema:
                {
                "name": string,
                "founded_year": string or null,
                "company_size": string or null,
                "headquarters": string or null,
                "industry": string or null,
                "description": string
                }"""
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

            return json.loads(content)

        except Exception as e:
            print("Ollama chat error:", e)
            return {
                "name": company_name,
                "founded_year": None,
                "company_size": None,
                "headquarters": None,
                "industry": None,
                "description": None
            }


    # -----------------------------
    # Main enrichment function
    # -----------------------------
    def enrich_lead(self, company_name, website):
        enrichment = {
            "company": company_name,
            "website": website,
            "description": self.scrape_about(website),
            "hiring": self.detect_hiring(website),
            "industry_keywords": [],
        }

        for kw in ["cafe", "tea", "food", "beverage", "retail", "restaurant"]:
            if kw in enrichment["description"].lower():
                enrichment["industry_keywords"].append(kw)

        enrichment.update(self.duckduckgo_signals(company_name))

        ddg_snippets = []
        queries = ["company size", "founded", "headquarters", "industry"]
        try:
            with DDGS() as ddgs:
                for q in queries:
                    query = f"{company_name} {q}"
                    results = list(ddgs.text(query, max_results=3))
                    for r in results:
                        snippet = (r.get("body") or "")
                        ddg_snippets.append(snippet)
        except Exception as e:
            print("DuckDuckGo error:", e)

        structured_info = self.parse_about_structured(enrichment["description"])
        ollama_info = self.extract_structured_info(ddg_snippets, company_name)
        if isinstance(ollama_info, dict):
            structured_info.update(ollama_info)
        enrichment["structured_info"] = structured_info

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
