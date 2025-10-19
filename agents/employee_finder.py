# agents/employee_finder.py
"""
Enhanced SalesEmployeeFinder with:
 - Configurable top % read from customer_requirements.json (default=15%)
 - Optional INDIA_FIRST flag for India-priority search
 - India-first employee search with global fallback (if enabled)
 - Robust DDGS with retries and logging
 - Deduplication, role filtering, and sanitized email guesses
"""

import time
import re
import random
import logging
import json
import os
from typing import List, Dict, Set
from dataclasses import dataclass
from ddgs import DDGS
import requests

# =====================
# CONFIGURATION
# =====================
INDIA_FIRST = True  # 🔁 Toggle this: True = India-first + fallback | False = global only

# =====================
# Logging
# =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
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
    source: str = ""
    confidence_score: float = 0.0
    likely_current: bool = True


# =====================
# Core Finder
# =====================
class SalesEmployeeFinder:
    def __init__(
        self,
        max_employees_per_company: int = 3,
        search_delay: float = 3.0,
        request_timeout: int = 12,
        ddgs_retries: int = 2
    ):
        self.max_employees = max_employees_per_company
        self.search_delay = search_delay
        self.request_timeout = request_timeout
        self.ddgs_retries = ddgs_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        self.title_separator_re = re.compile(r"\s*[-–—|]\s*")
        self.name_extract_re = re.compile(r"^([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*)")
        self.linkedin_profile_re = re.compile(r"(https?://)?(www\.)?linkedin\.com/in/[\w\-%]+", re.I)
        self.sales_keywords = [
            "sales", "business development", "bdm", "account executive",
            "account manager", "partnership", "growth", "enterprise sales",
            "sales manager", "regional sales"
        ]

    # -------------------------
    # MAIN EMPLOYEE SEARCH LOGIC
    # -------------------------
    def search_company_employees(self, company_name: str) -> List[Employee]:
        employees: List[Employee] = []
        seen_urls: Set[str] = set()

        # India-focused queries
        india_queries = [
            f'"sales" "at {company_name}" "India" site:linkedin.com/in',
            f'"business development" "at {company_name}" "India" site:linkedin.com/in',
            f'"account executive" "at {company_name}" "India" site:linkedin.com/in',
        ]

        # Global queries (always available)
        global_queries = [
            f'"sales" "at {company_name}" site:linkedin.com/in',
            f'"business development" "at {company_name}" site:linkedin.com/in',
            f'"account executive" "at {company_name}" site:linkedin.com/in',
        ]

        # =====================
        # Mode Control
        # =====================
        if INDIA_FIRST:
            logging.info(f"🔍 Searching (India-first) employees for: {company_name}")

            # Phase 1: Try India-first
            for query in india_queries:
                if len(employees) >= self.max_employees:
                    break
                results = self._perform_web_search_with_retries(query)
                found = self._extract_employee_info(results, company_name, india_only=True)
                for e in found:
                    if e.linkedin_url not in seen_urls:
                        employees.append(e)
                        seen_urls.add(e.linkedin_url)
                    if len(employees) >= self.max_employees:
                        break
                time.sleep(self.search_delay + random.uniform(0, 1.2))

            # Phase 2: Fallback to global if none found
            if not employees:
                logging.info(f"No India-based results for {company_name}. Falling back to global search.")
                for query in global_queries:
                    if len(employees) >= self.max_employees:
                        break
                    results = self._perform_web_search_with_retries(query)
                    found = self._extract_employee_info(results, company_name, india_only=False)
                    for e in found:
                        if e.linkedin_url not in seen_urls:
                            employees.append(e)
                            seen_urls.add(e.linkedin_url)
                        if len(employees) >= self.max_employees:
                            break
                    time.sleep(self.search_delay + random.uniform(0, 1.2))

        else:
            logging.info(f"🌐 Searching (Global-only) employees for: {company_name}")
            for query in global_queries:
                if len(employees) >= self.max_employees:
                    break
                results = self._perform_web_search_with_retries(query)
                found = self._extract_employee_info(results, company_name, india_only=False)
                for e in found:
                    if e.linkedin_url not in seen_urls:
                        employees.append(e)
                        seen_urls.add(e.linkedin_url)
                    if len(employees) >= self.max_employees:
                        break
                time.sleep(self.search_delay + random.uniform(0, 1.2))

        return employees[: self.max_employees]

    # -------------------------
    # DDGS WEB SEARCH
    # -------------------------
    def _perform_web_search_with_retries(self, query: str) -> Dict:
        backoff = 1.0
        for attempt in range(1, self.ddgs_retries + 2):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=12))
                    parsed = [
                        {'title': r.get('title', ''), 'href': r.get('href', ''), 'body': r.get('body', '')}
                        for r in results
                    ]
                    return {'results': parsed}
            except Exception as e:
                logging.warning(f"DDGS attempt {attempt} failed for query '{query}': {e}")
                time.sleep(backoff + random.uniform(0, 0.5))
                backoff *= 2
        logging.error(f"DDGS completely failed for query: {query}")
        return {'results': []}

    # -------------------------
    # PARSING HELPERS
    # -------------------------
    def _clean_name(self, raw: str) -> str:
        if not raw:
            return ""
        raw = re.sub(r"\|.*$", "", raw).strip()
        m = self.name_extract_re.search(raw)
        if m:
            return m.group(1).strip()
        parts = raw.split()
        caps = [p for p in parts if p and p[0].isupper()]
        if len(caps) >= 2:
            return " ".join(caps[:2])
        return parts[0] if parts else ""

    def _sanitize_company_for_email(self, company_name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", company_name.lower()) or "company"

    def _generate_email(self, name: str, company_name: str) -> str:
        if not name:
            return ""
        first = re.sub(r"[^a-z]", "", name.split()[0].lower())
        last = re.sub(r"[^a-z]", "", name.split()[-1].lower()) if len(name.split()) > 1 else ""
        domain = self._sanitize_company_for_email(company_name)
        return f"{first}.{last}@{domain}.com" if last else f"{first}@{domain}.com"

    def _is_sales_role(self, job_title: str) -> bool:
        s = (job_title or "").lower()
        return any(k in s for k in self.sales_keywords)

    # -------------------------
    # EXTRACT EMPLOYEE INFO
    # -------------------------
    def _extract_employee_info(self, search_results: Dict, company_name: str, india_only: bool = False) -> List[Employee]:
        employees: List[Employee] = []
        for res in search_results.get("results", []):
            url = (res.get("href") or "").strip()
            title = (res.get("title") or "").strip()
            body = (res.get("body") or "").strip()

            if not url or "linkedin.com/in" not in url.lower():
                continue

            if india_only and "india" not in (title.lower() + body.lower()):
                continue

            parts = self.title_separator_re.split(title)
            name_candidate = parts[0].strip() if parts else ""
            role_candidate = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
            name = self._clean_name(name_candidate)
            role = role_candidate or "Sales"

            if not self._is_sales_role(role):
                if not any(k in body.lower() for k in self.sales_keywords):
                    continue

            confidence = 0.7 if self._is_sales_role(role) else 0.5
            email = self._generate_email(name, company_name)

            emp = Employee(
                name=name,
                title=role,
                email=email,
                company=company_name,
                linkedin_url=url,
                source="linkedin",
                confidence_score=round(confidence, 2),
                likely_current=True
            )
            employees.append(emp)

        return employees


# =====================
# Main
# =====================
def main():
    inputs_dir = "outputs"
    outputs_dir = "outputs"
    os.makedirs(outputs_dir, exist_ok=True)

    scored_companies_file = os.path.join(inputs_dir, "scored_companies.json")
    requirements_file = os.path.join("inputs", "customer_requirements.json")
    employees_output_file = os.path.join(outputs_dir, "employees_companies.json")

    # Load customer requirements (for % config)
    try:
        with open(requirements_file, "r", encoding="utf-8") as f:
            customer_reqs = json.load(f)
        pct_default = float(customer_reqs.get("employee_search_top_percent", 0.15))
    except Exception:
        pct_default = 0.15

    # Load scored companies
    with open(scored_companies_file, "r", encoding="utf-8") as f:
        scored_companies = json.load(f)

    total = len(scored_companies)
    if total == 0:
        print("No scored companies found. Exiting.")
        return

    top_count = max(1, int(total * pct_default))
    logging.info(f"Configured to search top {pct_default*100:.0f}% ({top_count} of {total}) companies for employees.")
    logging.info(f"Search mode: {'India-first with fallback' if INDIA_FIRST else 'Global only'}")

    finder = SalesEmployeeFinder(max_employees_per_company=3, search_delay=2.0, request_timeout=12, ddgs_retries=2)

    results = []
    for comp in scored_companies[:top_count]:
        company_name = comp.get("company") or comp.get("company_name") or ""
        if not company_name:
            continue
        logging.info(f"Finding employees for {company_name} ...")
        try:
            employees = finder.search_company_employees(company_name)
        except Exception as e:
            logging.error(f"Error searching for {company_name}: {e}")
            employees = []

        results.append({
            "company": company_name,
            "num_found": len(employees),
            "employees": [
                {
                    "name": e.name,
                    "title": e.title,
                    "linkedin_url": e.linkedin_url,
                    "email_guess": e.email,
                    "confidence": e.confidence_score
                } for e in employees
            ]
        })

    with open(employees_output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Employee search complete! Results saved to {employees_output_file}")


if __name__ == "__main__":
    main()
