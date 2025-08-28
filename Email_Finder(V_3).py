import pandas as pd
import requests
import time
import re
import csv
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging
from ddgs import DDGS
from bs4 import BeautifulSoup
import random
from collections import Counter, defaultdict

# =====================
# Logging
# =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sales_finder.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# =====================
# Data Model
# =====================
@dataclass
class Employee:
    name: str
    title: str
    email: str
    company: str
    linkedin_url: str = ""
    source: str = ""  # linkedin / web_search / company_site
    confidence_score: float = 0.0
    likely_current: bool = True


# =====================
# Core Finder
# =====================
class SalesEmployeeFinder:
    def __init__(self, max_employees_per_company: int = 3, search_delay: int = 3, request_timeout: int = 12):
        self.max_employees = max_employees_per_company
        self.search_delay = search_delay
        self.request_timeout = request_timeout

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        self.common_domains: Dict[str, str] = {}

    # -----------------
    # CSV I/O
    # -----------------
    def read_companies_csv(self, file_path: str) -> List[str]:
        try:
            df = pd.read_csv(file_path)
            companies = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
            companies = list(dict.fromkeys([c for c in companies if c]))  # preserve order, drop blanks/dupes
            logging.info(f"Loaded {len(companies)} companies from {file_path}")
            return companies
        except Exception as e:
            logging.error(f"Error reading CSV: {e}")
            return []

    # -----------------
    # Main per-company search
    # -----------------
    def search_company_employees(self, company_name: str) -> List[Employee]:
        employees: List[Employee] = []

        company_domain = self._find_company_domain(company_name)
        if company_domain:
            logging.info(f"Using domain for {company_name}: {company_domain}")

        # Focused query set; avoid super broad queries
        search_queries = [
            f'"sales" "at {company_name}" site:linkedin.com/in',
            f'"business development" "at {company_name}" site:linkedin.com/in',
            f'"account executive" "at {company_name}" site:linkedin.com/in',
            f'"head of sales" "{company_name}" site:linkedin.com',
            f'"vp sales" "{company_name}" site:linkedin.com',
            f'"sales director" "{company_name}" site:linkedin.com',
            f'"{company_name}" "sales team"',
            f'"{company_name}" "our team" sales',
            f'"{company_name}" "leadership" sales',
        ]

        # Collect from web search
        per_query_results: List[List[Employee]] = []
        for query in search_queries:
            if len(employees) >= self.max_employees:
                break
            try:
                logging.info(f"Searching: {query}")
                results = self._perform_web_search(query)
                found = self._extract_employee_info_improved(results, company_name, company_domain)
                per_query_results.append(found)
                employees.extend(found)
                # polite delay
                time.sleep(self.search_delay + random.uniform(0, 1.5))
            except Exception as e:
                logging.error(f"Search error for '{company_name}': {e}")

        # Optional: scrape company site team/leadership pages for extra validation
        if company_domain and len(employees) < self.max_employees:
            try:
                site_emps = self._scrape_company_team_pages(company_domain, company_name)
                if site_emps:
                    employees.extend(site_emps)
            except Exception as e:
                logging.warning(f"Team page scrape failed for {company_domain}: {e}")

        # Deduplicate + consensus boost
        employees = self._deduplicate_and_consensus_boost(employees)

        # Sort by confidence and keep top-N
        employees.sort(key=lambda x: x.confidence_score, reverse=True)
        final = employees[: self.max_employees]

        logging.info(f"Found {len(final)} employees for {company_name}")
        return final

    # -----------------
    # Domain discovery
    # -----------------
    def _find_company_domain(self, company_name: str) -> Optional[str]:
        if company_name in self.common_domains:
            return self.common_domains[company_name]
        try:
            # two attempts for domain: "official website" and brand-only
            candidates: List[str] = []
            for q in [f'"{company_name}" official website', f'{company_name} website']:
                results = self._perform_web_search(q)
                for r in results.get('results', [])[:5]:
                    url = r.get('href', '')
                    if not url:
                        continue
                    dom = self._extract_domain_from_url(url)
                    if dom and self._is_likely_company_domain(dom, company_name):
                        candidates.append(dom)
            # choose the shortest (usually canonical)
            if candidates:
                domain = sorted(candidates, key=len)[0]
                self.common_domains[company_name] = domain
                return domain
        except Exception as e:
            logging.error(f"Domain lookup error for {company_name}: {e}")
        return None

    def _is_likely_company_domain(self, domain: str, company_name: str) -> bool:
        skip = (
            'linkedin.com','facebook.com','twitter.com','x.com','instagram.com','youtube.com',
            'crunchbase.com','wikipedia.org','bloomberg.com','reuters.com','forbes.com','medium.com'
        )
        if any(s in domain for s in skip):
            return False
        company_clean = re.sub(r'[^a-z0-9]', '', company_name.lower())
        domain_clean = re.sub(r'[^a-z0-9]', '', domain.lower().replace('www.', ''))
        if len(company_clean) >= 4 and (company_clean[:4] in domain_clean or company_clean[-4:] in domain_clean):
            return True
        # fallback contains
        return company_clean in domain_clean

    def _extract_domain_from_url(self, url: str) -> Optional[str]:
        try:
            from urllib.parse import urlparse
            netloc = urlparse(url).netloc.lower()
            netloc = netloc[4:] if netloc.startswith('www.') else netloc
            return netloc or None
        except Exception:
            return None

    # -----------------
    # Web search (DuckDuckGo via ddgs)
    # -----------------
    def _perform_web_search(self, query: str) -> Dict:
        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query=query, max_results=18, region='us-en', safesearch='moderate'))
                results = {
                    'results': [
                        {
                            'title': r.get('title', '') or '',
                            'href': r.get('href', '') or '',
                            'body': r.get('body', '') or ''
                        }
                        for r in search_results
                    ]
                }
                logging.info(f"Query returned {len(results['results'])} results: {query[:70]}…")
                return results
        except Exception as e:
            logging.error(f"DDGS search error: {e}")
            return {'results': []}

    # -----------------
    # Extraction & Filtering
    # -----------------
    def _extract_employee_info_improved(self, search_results: Dict, company_name: str, company_domain: Optional[str]) -> List[Employee]:
        employees: List[Employee] = []
        seen_names: set = set()
        company_lower = company_name.lower()

        for res in search_results.get('results', []):
            url = (res.get('href') or '').strip()
            title = (res.get('title') or '').strip()
            body = (res.get('body') or '').strip()
            combined_lower = f"{title} {body}".lower()

            # Must mention the company explicitly
            if company_lower not in combined_lower:
                continue

            # Exclude ex/former signals early
            if not self._is_current_employee(combined_lower):
                continue

            # Strongest: LinkedIn profile URLs
            if 'linkedin.com/in' in url.lower():
                emp = self._parse_linkedin_profile_result(title, body, url, company_name, company_domain)
                if emp and emp.name.lower() not in seen_names and self._is_sales_role(emp.title):
                    seen_names.add(emp.name.lower())
                    employees.append(emp)
                continue

            # General web snippets: look for "Name, <Sales Role> at Company"
            text_for_regex = f"{title} — {body}"
            pattern = rf"([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)[,\s]+([^,.\n]*?(?:sales|business development|account|revenue|commercial|partnership)[^,.\n]*)\s+(?:at|@)\s+{re.escape(company_name)}\b"
            for m in re.finditer(pattern, text_for_regex, flags=re.IGNORECASE):
                name = m.group(1).strip()
                role = m.group(2).strip()
                if not self._is_valid_name(name) or not self._is_sales_role(role):
                    continue
                email = self._generate_email(name, company_name, company_domain)
                score = 0.55
                if 'press' in url or 'news' in url:
                    score -= 0.1  # press can be out-of-date
                emp = Employee(
                    name=name,
                    title=role,
                    email=email,
                    company=company_name,
                    linkedin_url=url if 'linkedin.com' in url else '',
                    source='web_search',
                    confidence_score=max(0.0, min(1.0, score)),
                    likely_current=True
                )
                if emp.name.lower() not in seen_names:
                    seen_names.add(emp.name.lower())
                    employees.append(emp)

        return employees

    def _parse_linkedin_profile_result(self, title: str, body: str, url: str, company_name: str, company_domain: Optional[str]) -> Optional[Employee]:
        # Common LinkedIn title forms:
        # "Name - Title at Company | LinkedIn"
        # "Name | Title at Company - LinkedIn"
        # "Name – Title – Company | LinkedIn"
        candidates: List[Tuple[str, str, str]] = []  # (name, title, mentioned_company)
        patterns = [
            rf"^(?P<name>[A-Z][^\-|]+?)\s[\-|–]\s*(?P<title>[^\-|]+?)\s+(?:at|@)\s+(?P<company>[^\-|]+)",
            rf"^(?P<name>[A-Z][^\|]+?)\s\|\s*(?P<title>[^\|]+?)\s+(?:at|@)\s+(?P<company>[^\-|]+)",
            rf"^(?P<name>[A-Z][^\-|]+?)\s[\-|–]\s*(?P<title>[^\-|]+?)\s[\-|–]\s*(?P<company>[^\|]+)",
        ]
        headline = title.strip()
        for p in patterns:
            m = re.search(p, headline, flags=re.IGNORECASE)
            if m:
                candidates.append((m.group('name').strip(), m.group('title').strip(), m.group('company').strip()))
                break

        # Fallback: glean from snippet if title parse failed
        if not candidates:
            m2 = re.search(rf"([A-Z][a-z]+(?:\s[A-Z][a-z]+)+).*?\bat\s+{re.escape(company_name)}\b", f"{title} {body}", flags=re.IGNORECASE)
            if m2:
                name = m2.group(1).strip()
                # Try to extract role words around name
                role_match = re.search(r"(sales[^\-|,]*)", f"{title} {body}", flags=re.IGNORECASE)
                role = role_match.group(1).strip() if role_match else 'Sales'
                candidates.append((name, role, company_name))

        if not candidates:
            return None

        name, role, mentioned_company = candidates[0]
        if not (self._is_valid_name(name) and self._company_names_match(mentioned_company, company_name)):
            return None

        likely_current = self._is_current_employee(f"{title} {body}")
        email = self._generate_email(name, company_name, company_domain)

        score = 0.7  # base for LinkedIn match + company mention
        if ' at ' in (title + ' ' + body).lower():
            score += 0.1
        if company_domain:
            score += 0.05
        if not self._is_sales_role(role):
            score -= 0.25

        return Employee(
            name=name,
            title=role,
            email=email,
            company=company_name,
            linkedin_url=url,
            source='linkedin',
            confidence_score=max(0.0, min(1.0, score)),
            likely_current=likely_current
        )

    # -----------------
    # Company site scraping (optional, conservative)
    # -----------------
    def _scrape_company_team_pages(self, domain: str, company_name: str) -> List[Employee]:
        paths = [
            '/', '/about', '/about-us', '/team', '/our-team', '/leadership', '/management', '/company', '/people'
        ]
        found: List[Employee] = []
        seen_names: set = set()

        for p in paths:
            url = f"https://{domain}{p}"
            try:
                resp = self.session.get(url, timeout=self.request_timeout)
                if resp.status_code != 200 or 'text/html' not in resp.headers.get('Content-Type', ''):
                    continue
                soup = BeautifulSoup(resp.text, 'html.parser')

                # Heuristic: blocks that have a name-like heading and nearby role
                name_tags = soup.select('h1, h2, h3, h4, strong, b')
                for tag in name_tags:
                    name = (tag.get_text(strip=True) or '').strip()
                    if not self._is_valid_name(name):
                        continue

                    # look around for role text
                    role_text = ''
                    # siblings
                    sib = tag.find_next_sibling()
                    if sib:
                        role_text = sib.get_text(" ", strip=True)[:120]
                    # parent
                    if not role_text and tag.parent:
                        role_text = tag.parent.get_text(" ", strip=True)[:160]

                    if not role_text:
                        continue

                    if self._is_sales_role(role_text) and name.lower() not in seen_names:
                        email = self._generate_email(name, company_name, domain)
                        emp = Employee(
                            name=name,
                            title=self._clean_role(role_text),
                            email=email,
                            company=company_name,
                            linkedin_url='',
                            source='company_site',
                            confidence_score=0.65,  # company site is fairly trustworthy
                            likely_current=True
                        )
                        seen_names.add(name.lower())
                        found.append(emp)

                if len(found) >= self.max_employees:
                    break

            except Exception as e:
                logging.debug(f"Team page fetch failed for {url}: {e}")
                continue

        return found

    # -----------------
    # Utilities
    # -----------------
    def _is_current_employee(self, text_lower: str) -> bool:
        bad_terms = ["former", "ex-", "previously", "past ", "alumni", "retired", "ex employee", "ex-employee"]
        return not any(bt in text_lower for bt in bad_terms)

    def _company_names_match(self, a: str, b: str) -> bool:
        def clean(x: str) -> str:
            x = x.lower()
            x = re.sub(r"\b(inc|corp|llc|ltd|plc|pvt|private|company|co|limited)\b", "", x)
            x = x.replace('&', 'and')
            x = re.sub(r'[^a-z0-9 ]', '', x)
            return re.sub(r"\s+", " ", x).strip()
        ca, cb = clean(a), clean(b)
        return ca in cb or cb in ca

    def _is_valid_name(self, name: str) -> bool:
        if not name:
            return False
        parts = name.strip().split()
        if len(parts) < 2 or len(parts) > 5:
            return False
        invalid = {"team", "contact", "careers", "sales", "marketing", "linkedin", "profile", "company"}
        if any(p.lower() in invalid for p in parts):
            return False
        # ensure capitalization pattern
        return all(p[0].isupper() for p in parts if p)

    def _clean_role(self, text: str) -> str:
        # compress whitespace and cut after 80 chars
        t = re.sub(r"\s+", " ", text).strip()
        return t[:80]

    def _is_sales_role(self, job_title: str) -> bool:
        if not job_title:
            return False
        s = job_title.lower()
        keywords = [
            'sales', 'business development', 'account manager', 'account executive', 'revenue', 'commercial',
            'customer success', 'partnership', 'growth', 'sales representative', 'sales consultant',
            'inside sales', 'outside sales', 'field sales', 'regional sales', 'channel sales',
            'vp sales', 'vice president sales', 'head of sales', 'sales director', 'chief sales officer', 'cso',
            'enterprise sales', 'bdm', 'bde'
        ]
        return any(k in s for k in keywords)

    def _generate_email(self, name: str, company_name: str, company_domain: Optional[str]) -> str:
        if not name or len(name.split()) < 2:
            return ''
        domain = company_domain if company_domain else self._guess_email_domain(company_name)
        if not domain:
            return ''
        first, last = name.lower().split()[0], name.lower().split()[-1]
        return f"{first}.{last}@{domain}"

    def _guess_email_domain(self, company_name: str) -> str:
        name_clean = re.sub(r'[^a-z0-9 ]', '', company_name.lower())
        name_clean = re.sub(r"\b(inc|corp|llc|ltd|plc|pvt|co|company|limited)\b", '', name_clean).strip()
        parts = [w for w in name_clean.split() if len(w) > 1]
        if not parts:
            return ''
        if len(parts) == 1:
            return f"{parts[0]}.com"
        return f"{parts[0]}{parts[1]}.com"

    def _deduplicate_and_consensus_boost(self, employees: List[Employee]) -> List[Employee]:
        # Keep best per (name, company); boost if multiple sources mention the same person
        bucket: Dict[Tuple[str, str], List[Employee]] = defaultdict(list)
        for e in employees:
            bucket[(e.name.lower(), e.company.lower())].append(e)

        final: List[Employee] = []
        for key, group in bucket.items():
            # pick the highest-confidence instance
            best = max(group, key=lambda x: x.confidence_score)
            # consensus boost for multiple distinct sources
            distinct_sources = {g.source for g in group}
            if len(group) >= 2:
                best.confidence_score = min(1.0, best.confidence_score + 0.15)
            if len(distinct_sources) >= 2:
                best.confidence_score = min(1.0, best.confidence_score + 0.1)
            final.append(best)

        # filter: must be sales role and likely current
        final = [f for f in final if self._is_sales_role(f.title) and f.likely_current]
        return final

    # -----------------
    # Batch processing & CSV
    # -----------------
    def process_companies(self, input_csv_path: str, output_csv_path: str):
        companies = self.read_companies_csv(input_csv_path)
        if not companies:
            logging.error("No companies found in CSV")
            return

        all_employees: List[Employee] = []
        processed = 0

        print(f"Processing {len(companies)} companies…")
        for i, company in enumerate(companies, 1):
            try:
                logging.info(f"=== {i}/{len(companies)}: {company} ===")
                emps = self.search_company_employees(company)
                all_employees.extend(emps)
                processed += 1
                print(f"Progress: {i}/{len(companies)} — {company}: {len(emps)} employees")
                if i % 10 == 0:
                    self.save_results_to_csv(all_employees, output_csv_path.replace('.csv', '_temp.csv'))
            except Exception as e:
                logging.error(f"Error processing {company}: {e}")

        self.save_results_to_csv(all_employees, output_csv_path)
        print("\n=== Processing Complete ===")
        print(f"Companies processed: {processed}/{len(companies)}")
        print(f"Total employees found: {len(all_employees)}")
        avg = len(all_employees)/processed if processed else 0
        print(f"Average employees per company: {avg:.2f}")
        print(f"Results saved to: {output_csv_path}")

    def save_results_to_csv(self, employees: List[Employee], output_path: str):
        try:
            employees.sort(key=lambda x: (x.company.lower(), -x.confidence_score, x.name.lower()))
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=['company', 'name', 'title', 'email', 'linkedin_url', 'confidence_score', 'likely_current', 'source']
                )
                writer.writeheader()
                for e in employees:
                    writer.writerow({
                        'company': e.company,
                        'name': e.name,
                        'title': e.title,
                        'email': e.email,
                        'linkedin_url': e.linkedin_url,
                        'confidence_score': round(e.confidence_score, 2),
                        'likely_current': 'Yes' if e.likely_current else 'No',
                        'source': e.source,
                    })
            logging.info(f"Saved {len(employees)} employees -> {output_path}")
        except Exception as e:
            logging.error(f"CSV save error: {e}")


# =====================
# Main
# =====================

def main():
    INPUT_CSV = r"C:\\Users\\pulki\\Downloads\\companies.csv"
    OUTPUT_CSV = r"C:\\Users\\pulki\\Downloads\\verified_sales_employees.csv"
    MAX_EMPLOYEES_PER_COMPANY = 3
    SEARCH_DELAY = 4

    print("🔍 Sales Employee Finder (High-Accuracy / Free)")
    print("- Filters ex-employees")
    print("- Prefers LinkedIn profiles with 'at <Company>'")
    print("- Optional company-site team scraping for validation")
    print("- Consensus boosting across multiple queries")

    finder = SalesEmployeeFinder(max_employees_per_company=MAX_EMPLOYEES_PER_COMPANY, search_delay=SEARCH_DELAY)
    finder.process_companies(INPUT_CSV, OUTPUT_CSV)


if __name__ == "__main__":
    main()
