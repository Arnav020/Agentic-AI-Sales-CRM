# agents/enrichment_agent.py
# Do "ollama pull mistral:latest" and then "ollama serve"
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from ollama import chat
import json
import re
import time
import os


class EnrichmentAgent:
    def __init__(self, model="mistral:latest"):
        self.model = model

        # Expanded keyword → standardized industry mapping
        self.industry_map = {
            # Food & Beverage
            "cafe": "Food & Beverage",
            "tea": "Food & Beverage",
            "coffee": "Food & Beverage",
            "snack": "Food & Beverage",
            "restaurant": "Food & Beverage",
            "franchise": "Food & Beverage",
            "bakery": "Food & Beverage",
            "fast food": "Food & Beverage",
            "dining": "Food & Beverage",
            "outlet": "Food & Beverage",
            "chain": "Food & Beverage",

            # Technology
            "software": "Technology",
            "it services": "Technology",
            "information technology": "Technology",
            "technology": "Technology",
            "saas": "Technology",
            "cloud": "Technology",
            "artificial intelligence": "Technology",
            "machine learning": "Technology",
            "data": "Technology",
            "cybersecurity": "Technology",
            "consulting": "Technology",
            "automation": "Technology",
            "blockchain": "Technology",
            "iot": "Technology",

            # Finance
            "banking": "Finance",
            "fintech": "Finance",
            "insurance": "Finance",
            "lending": "Finance",
            "investment": "Finance",
            "trading": "Finance",
            "mutual fund": "Finance",
            "capital market": "Finance",
            "wealth management": "Finance",
            "payment gateway": "Finance",

            # Healthcare
            "hospital": "Healthcare",
            "clinic": "Healthcare",
            "pharma": "Healthcare",
            "pharmaceutical": "Healthcare",
            "biotech": "Healthcare",
            "diagnostics": "Healthcare",
            "healthcare": "Healthcare",
            "telemedicine": "Healthcare",
            "medical devices": "Healthcare",
            "wellness": "Healthcare",

            # Manufacturing & Energy
            "manufacturing": "Manufacturing",
            "factory": "Manufacturing",
            "automobile": "Manufacturing",
            "electronics": "Manufacturing",
            "engineering": "Manufacturing",
            "renewable": "Energy",
            "solar": "Energy",
            "oil": "Energy",
            "gas": "Energy",
            "energy": "Energy",
            "power plant": "Energy",

            # Education
            "edtech": "Education",
            "education": "Education",
            "university": "Education",
            "school": "Education",
            "training": "Education",
            "elearning": "Education",
            "coaching": "Education"
        }

        # City regex for HQ detection (extendable)
        self.city_regex = re.compile(
            r"\b(New Delhi|Delhi|Gurugram|Bangalore|Bengaluru|Mumbai|Pune|Hyderabad|Chennai|Kolkata|Noida|Ahmedabad)\b",
            re.I
        )

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
            except Exception as e:
                print(f"About page scrape failed for {website}: {e}")
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
        try:
            with DDGS() as ddgs:
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
                for key, query in queries.items():
                    try:
                        results = list(ddgs.text(query, max_results=5))
                        score = 0
                        for r in results:
                            snippet = (r.get("body") or "").lower()
                            for kw in keywords[key]:
                                if kw in snippet:
                                    score += 0.3 if key != "negative_signal" else 0.5
                        signals[key] = min(1.0, round(score, 2))
                    except Exception as e:
                        print(f"DDG query failed for {company_name} ({key}): {e}")
        except Exception as e:
            print("DuckDuckGo initialization failed:", e)

        # Calibration
        if signals["expansion_signal"] >= 0.5 or signals["funding_signal"] >= 0.5:
            signals["negative_signal"] = min(signals["negative_signal"], 0.2)

        return signals

    # -----------------------------
    # Structured Info Extraction
    # -----------------------------
    def extract_structured_info(self, snippets, company_name):
        snippets_text = " ".join(snippets)[:2000]
        snippets_text = re.sub(r'[\r\n]+', ' ', snippets_text)
        snippets_text = re.sub(r'["]', "'", snippets_text)

        founded_year = "Unknown"
        year_match = re.search(r"(founded\s+in\s+|established\s+in\s+)(\d{4})", snippets_text, re.I)
        if year_match:
            founded_year = year_match.group(2)

        employees = "Unknown"
        emp_match = re.search(r"(\d{2,6})\+?\s+(employees|staff)", snippets_text, re.I)
        if emp_match:
            employees = emp_match.group(1)

        headquarters = "Unknown"
        city_match = self.city_regex.search(snippets_text)
        if city_match:
            headquarters = city_match.group(1)

        messages = [
            {"role": "system", "content": "You are a company info extractor. Return ONLY valid JSON in a single line. Use 'Unknown' if field not found."},
            {"role": "user", "content": f"Extract structured info about {company_name} from this text:\n{snippets_text}"}
        ]

        info = {}
        try:
            response = chat(model=self.model, messages=messages, options={"temperature": 0, "top_p": 1})
            content = response['message']['content'].strip()
            content = re.sub(r"^```(json)?|```$", "", content, flags=re.MULTILINE).strip()
            info = json.loads(content)
        except Exception as e:
            print(f"Ollama chat error for {company_name}: {e}")
            info = {}

        return {
            "name": info.get("name") or company_name,
            "founded_year": info.get("founded_year") or founded_year,
            "employees_count": info.get("employees_count") or employees,
            "headquarters": info.get("headquarters") or headquarters,
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

        # Industry inference
        desc_lower = enrichment["description"].lower()
        keywords_found = []
        industry_guess = None
        for kw, mapped_industry in self.industry_map.items():
            if kw in desc_lower:
                keywords_found.append(kw)
                industry_guess = mapped_industry if not industry_guess else industry_guess
        enrichment["industry_keywords"] = list(set(keywords_found))

        # Add signals
        try:
            enrichment.update(self.duckduckgo_signals(company_name))
        except Exception as e:
            print(f"Skipping DDG signals for {company_name} due to error: {e}")

        # Collect DDG snippets
        ddg_snippets = []
        queries = ["company size", "founded", "headquarters", "industry"]
        try:
            with DDGS() as ddgs:
                for q in queries:
                    try:
                        results = list(ddgs.text(f"{company_name} {q}", max_results=3))
                        for r in results:
                            ddg_snippets.append(r.get("body") or "")
                    except Exception as e:
                        print(f"DDG snippet fetch failed for {company_name} ({q}): {e}")
        except Exception as e:
            print(f"DDG initialization failed for {company_name}: {e}")

        # Structured info extraction
        ollama_info = self.extract_structured_info(ddg_snippets, company_name)
        if ollama_info["industry"] == "Unknown" and industry_guess:
            ollama_info["industry"] = industry_guess

        enrichment["structured_info"] = ollama_info
        return enrichment


# -----------------------------
# Run Multiple Companies Safely
# -----------------------------
if __name__ == "__main__":
    agent = EnrichmentAgent(model="mistral:latest")

    # Load companies.json
    input_file = os.path.join("inputs", "companies.json")
    with open(input_file, "r", encoding="utf-8") as f:
        companies = json.load(f)

    all_enriched = []

    for comp in companies:
        print(f"\nEnriching: {comp['name']} ...")
        try:
            enriched_data = agent.enrich_lead(comp["name"], comp["website"])
        except Exception as e:
            print(f"Failed to enrich {comp['name']}: {e}")
            enriched_data = {"company": comp['name'], "error": str(e)}
        all_enriched.append(enriched_data)
        time.sleep(1)  # small delay to reduce network issues

    # Save to outputs/enriched_companies.json
    os.makedirs("outputs", exist_ok=True)
    output_file = os.path.join("outputs", "enriched_companies.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_enriched, f, indent=2, ensure_ascii=False)

    print(f"\nEnrichment complete! Saved to {output_file}")
