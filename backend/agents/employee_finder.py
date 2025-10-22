# agents/employee_finder.py
"""
Multi-user compatible SalesEmployeeFinder
------------------------------------------
- Per-user inputs/outputs under /users/<user_id>/
- Writes logs to /users/<user_id>/logs/employee_finder.log
- Reads customer_requirements.json for top % configuration
- Saves results both locally (JSON) and to MongoDB
- Core logic unchanged
"""

import time
import re
import random
import logging
import json
import os
from typing import List, Dict, Set
from dataclasses import dataclass
from pathlib import Path
from ddgs import DDGS
import requests
from datetime import datetime

# Import MongoDB helper (backend integration)
from backend.db.mongo import mongo_save_result
from backend.db.mongo import save_user_output


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
        user_root: str = None,
        max_employees_per_company: int = 3,
        search_delay: float = 3.0,
        request_timeout: int = 12,
        ddgs_retries: int = 2,
        india_first: bool = True
    ):
        """
        user_root → path to the user's workspace (e.g. users/user_demo)
        """
        self.project_root = Path(__file__).resolve().parents[1]
        self.user_root = Path(user_root) if user_root else self.project_root

        # --- Directories ---
        self.inputs_dir = self.user_root / "inputs"
        self.outputs_dir = self.user_root / "outputs"
        self.logs_dir = self.user_root / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

        # --- Logging ---
        self.log_file = self.logs_dir / "employee_finder.log"
        self._setup_logging()

        # --- Configurable attributes ---
        self.max_employees = max_employees_per_company
        self.search_delay = search_delay
        self.request_timeout = request_timeout
        self.ddgs_retries = ddgs_retries
        self.india_first = india_first

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })

        # --- Regex & keywords ---
        self.title_separator_re = re.compile(r"\s*[-–—|]\s*")
        self.name_extract_re = re.compile(r"^([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*)")
        self.linkedin_profile_re = re.compile(r"(https?://)?(www\.)?linkedin\.com/in/[\w\-%]+", re.I)
        self.sales_keywords = [
            "sales", "business development", "bdm", "account executive",
            "account manager", "partnership", "growth", "enterprise sales",
            "sales manager", "regional sales"
        ]

    # -------------------------
    # Logging Setup
    # -------------------------
    def _setup_logging(self):
        logging.getLogger().handlers = []
        logging.basicConfig(
            filename=str(self.log_file),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(console)
        logging.info(f"Logging initialized for EmployeeFinder → {self.log_file}")

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

        # Global queries
        global_queries = [
            f'"sales" "at {company_name}" site:linkedin.com/in',
            f'"business development" "at {company_name}" site:linkedin.com/in',
            f'"account executive" "at {company_name}" site:linkedin.com/in',
        ]

        if self.india_first:
            logging.info(f"🔍 Searching (India-first) employees for: {company_name}")

            # Phase 1: India-first
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

            # Phase 2: fallback
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

    # -------------------------
    # RUNNER
    # -------------------------
    def run(self):
        logging.info("🚀 Starting employee finder...")

        scored_companies_file = self.outputs_dir / "scored_companies.json"
        requirements_file = self.inputs_dir / "customer_requirements.json"
        employees_output_file = self.outputs_dir / "employees_companies.json"

        if not scored_companies_file.exists() or not requirements_file.exists():
            logging.error("❌ Missing input files. Make sure scoring_agent and inputs are ready.")
            return

        try:
            with open(requirements_file, "r", encoding="utf-8") as f:
                customer_reqs = json.load(f)
            pct_default = float(customer_reqs.get("employee_search_top_percent", 0.15))
        except Exception:
            pct_default = 0.15

        with open(scored_companies_file, "r", encoding="utf-8") as f:
            scored_companies = json.load(f)

        total = len(scored_companies)
        if total == 0:
            logging.warning("No scored companies found. Exiting.")
            return

        top_count = max(1, int(total * pct_default))
        logging.info(f"Configured to search top {pct_default*100:.0f}% ({top_count} of {total}) companies.")
        logging.info(f"Search mode: {'India-first with fallback' if self.india_first else 'Global only'}")

        results = []
        for comp in scored_companies[:top_count]:
            company_name = comp.get("company") or comp.get("company_name") or ""
            if not company_name:
                continue
            logging.info(f"Finding employees for {company_name} ...")
            try:
                employees = self.search_company_employees(company_name)
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

        # --- Save to local JSON
        with open(employees_output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logging.info(f"✅ Employee search complete. Results saved to {employees_output_file}")
        print(f"✅ Employee search complete. Results saved to {employees_output_file}")

        # --- Save to MongoDB ---
        try:
            doc = {
                "user_id": self.user_root.name,
                "created_at": datetime.utcnow(),
                "count": len(results),
                "results": results,
            }
            mongo_save_result("employee_finder", doc)
            logging.info(f"Saved employee results to MongoDB (user={self.user_root.name}, count={len(results)})")
        except Exception as e:
            logging.error(f"Mongo save failed: {e}")
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_path = self.outputs_dir / f"employee_backup_{ts}.json"
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logging.info(f"Backup JSON saved → {backup_path}")

        try:
            user_id = self.user_root.name if self.user_root else "unknown"
            save_user_output(user_id=user_id, agent="employee_finder", output_type="employees_companies", data={"results": results})
            logging.info("Saved employee finder results to user_outputs (mongo)")
        except Exception:
            logging.exception("Failed to save employee finder results to user_outputs")


# =====================
# Runner / Entrypoint for both Orchestrator and Standalone use
# =====================
def main(user_folder: str | None = None):
    """
    Main entrypoint for SalesEmployeeFinder.
    Supports both:
      • Orchestrator import: main("users/user_demo")
      • Standalone CLI: python agents/employee_finder.py user_demo
    """
    if user_folder:
        user_path = Path(user_folder)
    else:
        env_user = os.getenv("USER_FOLDER")
        user_path = Path(env_user) if env_user else None

    finder = SalesEmployeeFinder(user_root=user_path)
    finder.run()


if __name__ == "__main__":
    import sys
    user_arg = sys.argv[1] if len(sys.argv) >= 2 else None
    if user_arg:
        user_folder = str(Path("users") / user_arg)
    else:
        user_folder = None

    main(user_folder)
