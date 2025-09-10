# agents/employee_finder.py
import time
import re
import random
import logging
import json
import os
from typing import List, Dict
from dataclasses import dataclass
from ddgs import DDGS
import requests

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
    def __init__(self, max_employees_per_company: int = 3, search_delay: int = 3, request_timeout: int = 12):
        self.max_employees = max_employees_per_company
        self.search_delay = search_delay
        self.request_timeout = request_timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })

    def search_company_employees(self, company_name: str) -> List[Employee]:
        employees: List[Employee] = []

        # Search queries
        search_queries = [
            f'"sales" "at {company_name}" site:linkedin.com/in',
            f'"business development" "at {company_name}" site:linkedin.com/in',
            f'"account executive" "at {company_name}" site:linkedin.com/in',
        ]

        for query in search_queries:
            if len(employees) >= self.max_employees:
                break
            logging.info(f"Searching: {query}")
            results = self._perform_web_search(query)
            found = self._extract_employee_info(results, company_name)
            employees.extend(found)
            time.sleep(self.search_delay + random.uniform(0, 1.5))

        return employees[: self.max_employees]

    def _perform_web_search(self, query: str) -> Dict:
        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query=query, max_results=10))
                return {
                    'results': [{'title': r.get('title', ''), 'href': r.get('href', ''), 'body': r.get('body', '')} for r in search_results]
                }
        except Exception as e:
            logging.error(f"DDGS search error: {e}")
            return {'results': []}

    def _extract_employee_info(self, search_results: Dict, company_name: str) -> List[Employee]:
        employees: List[Employee] = []
        for res in search_results.get("results", []):
            url = res.get("href", "")
            title = res.get("title", "")

            # Only LinkedIn profile results
            if "linkedin.com/in" in url.lower():
                # Parse name + title
                match = re.match(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)\s*[-|–|]\s*(.*)", title)
                if match:
                    name = match.group(1).strip()
                    role = match.group(2).strip()
                else:
                    name = title.split("-")[0].strip()
                    role = "Sales"

                if self._is_sales_role(role):
                    emp = Employee(
                        name=name,
                        title=role,
                        email=f"{name.split()[0].lower()}.{name.split()[-1].lower()}@{company_name.lower().replace(' ', '')}.com",
                        company=company_name,
                        linkedin_url=url,
                        source="linkedin",
                        confidence_score=0.7,
                        likely_current=True
                    )
                    employees.append(emp)
        return employees

    def _is_sales_role(self, job_title: str) -> bool:
        if not job_title:
            return False
        s = job_title.lower()
        keywords = ["sales", "business development", "account executive", "partnership", "growth"]
        return any(k in s for k in keywords)


# =====================
# Main
# =====================
def main():
    inputs_dir = "outputs"
    outputs_dir = "outputs"

    scored_companies_file = os.path.join(inputs_dir, "scored_companies.json")
    employees_output_file = os.path.join(outputs_dir, "employees_companies.json")

    # Load scored companies
    with open(scored_companies_file, "r", encoding="utf-8") as f:
        scored_companies = json.load(f)

    # Ask user for how many companies to take
    top_n = input("Enter number of top companies to fetch employees for (default=5): ").strip()
    top_n = int(top_n) if top_n.isdigit() else 5

    finder = SalesEmployeeFinder(max_employees_per_company=3, search_delay=2)

    results = []
    for comp in scored_companies[:top_n]:
        company_name = comp["company"]
        logging.info(f"🔍 Finding employees for {company_name}...")
        employees = finder.search_company_employees(company_name)

        results.append({
            "company": company_name,
            "employees": [
                {
                    "name": e.name,
                    "title": e.title,
                    "linkedin_url": e.linkedin_url
                } for e in employees
            ]
        })

    # Save to JSON
    with open(employees_output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Employee search complete! Results saved to {employees_output_file}")


if __name__ == "__main__":
    main()
