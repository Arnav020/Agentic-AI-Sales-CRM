# agents/contact_finder.py
"""
Agentic CRM Contact Finder (Sequential Multi-Account Verifalia)
 - Uses up to 3 Verifalia accounts sequentially (no wraparound)
 - Verifies only ONE best employee per company (fallbacks only if needed)
 - Always keeps consistent JSON output schema
 - Stops gracefully when all accounts exhausted
"""

import time
import logging
import base64
import json
import os
import re
from typing import List, Dict
from dataclasses import dataclass
import requests
from dotenv import load_dotenv

# =====================
# Setup & Logging
# =====================
load_dotenv()
os.makedirs("logs", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
logging.basicConfig(
    filename="logs/contact_finder.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# =====================
# Config
# =====================
MAX_RETRIES = 3
RETRY_BACKOFF = 2
API_BASE = "https://api.verifalia.com/v2.7"

# =====================
# Data Model
# =====================
@dataclass
class Employee:
    name: str
    title: str
    company: str
    linkedin_url: str = ""
    email: str = ""
    verified_email: str = ""
    email_verified: bool = False
    email_classification: str = "Unknown"
    confidence_score: float = 0.0


# =====================
# Email Pattern Generator (Weighted Order)
# =====================
class EmailPermutationGenerator:
    @staticmethod
    def generate(name: str, company: str) -> List[str]:
        """Generate common business email patterns, sorted by likelihood of correctness."""
        if not name or not company:
            return []

        parts = re.sub(r"[^a-zA-Z\s]", "", name.lower()).split()
        if not parts:
            return []

        first = parts[0]
        last = parts[-1] if len(parts) > 1 else ""
        domain = re.sub(r"[^a-z0-9]", "", company.lower()) + ".com"

        # Candidate patterns with relative likelihood weights
        candidates = []

        if last:
            candidates = [
                (f"{first}.{last}@{domain}", 0.36),
                (f"{first}@{domain}", 0.26),
                (f"{first}{last}@{domain}", 0.14),
                (f"{first[0]}{last}@{domain}", 0.10),
                (f"{first}_{last}@{domain}", 0.06),
                (f"{first[0]}.{last}@{domain}", 0.04),
                (f"{last}.{first}@{domain}", 0.02),
                (f"{first}.{last[0]}@{domain}", 0.02),
            ]
        else:
            candidates = [
                (f"{first}@{domain}", 0.5),
                (f"{first[0]}@{domain}", 0.2),
                (f"{first}1@{domain}", 0.1),
                (f"{first}.{first[0]}@{domain}", 0.05),
            ]

        # Sort by weight descending, remove duplicates
        sorted_candidates = sorted(candidates, key=lambda x: -x[1])
        patterns = list(dict.fromkeys([c[0] for c in sorted_candidates]))

        return patterns



# =====================
# Verifalia Verifier
# =====================
class VerifaliaVerifier:
    def __init__(self, accounts: List[Dict[str, str]]):
        self.accounts = accounts
        self.current_idx = 0
        self.session = requests.Session()
        self.out_of_credits = False
        self._set_auth_header()

    def _set_auth_header(self):
        creds = self.accounts[self.current_idx]
        auth = base64.b64encode(f"{creds['user']}:{creds['pass']}".encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "User-Agent": f"AgenticCRM/EmailVerifier/{self.current_idx+1}"
        })
        logging.info(f"🔐 Using Verifalia account #{self.current_idx+1}: {creds['user']}")

    def _rotate_account(self):
        if self.current_idx + 1 < len(self.accounts):
            self.current_idx += 1
            self._set_auth_header()
            logging.info(f"🔁 Switched to Verifalia account #{self.current_idx+1}")
            time.sleep(1.0)
        else:
            logging.error("❌ All Verifalia accounts exhausted. Stopping verification.")
            self.out_of_credits = True

    def verify_email(self, email: str) -> Dict:
        """Submit email to Verifalia API."""
        if self.out_of_credits:
            return self._default_result(email, "all_accounts_exhausted")

        payload = {"entries": [{"inputData": email}], "quality": "Standard"}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = self.session.post(f"{API_BASE}/email-validations", json=payload, timeout=20)

                if r.status_code == 202:
                    job_id = r.json().get("overview", {}).get("id")
                    return self._poll_for_results(job_id)
                elif r.status_code == 200:
                    return self._parse_result(r.json())
                elif r.status_code in (401, 402, 429):
                    logging.warning(f"⚠️ Account #{self.current_idx+1} hit limit ({r.status_code}).")
                    self._rotate_account()
                    return self._default_result(email, "rotated_account")
                else:
                    logging.warning(f"Unexpected response {r.status_code}: {r.text}")
                    time.sleep(RETRY_BACKOFF)
            except Exception as e:
                logging.error(f"Error verifying {email}: {e}")
                time.sleep(RETRY_BACKOFF)
        return self._default_result(email, "api_error")

    def _poll_for_results(self, job_id: str, max_wait: int = 10) -> Dict:
        for _ in range(max_wait):
            try:
                r = self.session.get(f"{API_BASE}/email-validations/{job_id}", timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("overview", {}).get("status") == "Completed":
                        return self._parse_result(data)
                time.sleep(2)
            except Exception as e:
                logging.warning(f"Polling failed for {job_id}: {e}")
        return self._default_result("", "timeout")

    def _parse_result(self, data: Dict) -> Dict:
        try:
            entries = data.get("entries", {}).get("data", [])
            if not entries:
                return self._default_result("", "no_entries")
            entry = entries[0]
            email = entry.get("inputData", "")
            classification = entry.get("classification", "Unknown")
            conf_map = {"Deliverable": 0.95, "Risky": 0.5, "Unknown": 0.2, "Undeliverable": 0.0}
            return {
                "email": email,
                "is_valid": classification == "Deliverable",
                "classification": classification,
                "confidence": conf_map.get(classification, 0.1),
                "verified": True
            }
        except Exception as e:
            logging.error(f"Parse error: {e}")
            return self._default_result("", "parse_error")

    def _default_result(self, email: str, reason: str) -> Dict:
        return {
            "email": email,
            "is_valid": False,
            "classification": "Unknown",
            "confidence": 0.0,
            "verified": False,
            "error": reason
        }


# =====================
# Main Runner
# =====================
def verify_emails_from_json(input_file: str, output_file: str):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    accounts = []
    for i in range(1, 4):
        u = os.getenv(f"VERIFALIA_USER_{i}")
        p = os.getenv(f"VERIFALIA_PASS_{i}")
        if u and p:
            accounts.append({"user": u, "pass": p})
    if not accounts:
        u = os.getenv("VERIFALIA_USER", "ajoshi4_be23@thapar.edu")
        p = os.getenv("VERIFALIA_PASS", "")
        accounts.append({"user": u, "pass": p})

    verifier = VerifaliaVerifier(accounts)

    verified_count = 0
    skipped_count = 0

    for company in data:
        company_name = company.get("company", "")
        employees = company.get("employees", [])
        if not employees:
            continue

        # Sort by confidence descending
        employees_sorted = sorted(employees, key=lambda e: e.get("confidence", 0), reverse=True)

        found_valid = False
        verified_emp = None

        for emp in employees_sorted:
            if verifier.out_of_credits:
                company["verification_status"] = "skipped_out_of_credit"
                skipped_count += 1
                break

            full_name = emp.get("name", "")
            email_candidates = EmailPermutationGenerator.generate(full_name, company_name)
            logging.info(f"🔍 Checking {full_name} from {company_name}...")

            for candidate in email_candidates:
                result = verifier.verify_email(candidate)
                emp["verified_email"] = candidate
                emp["email_verified"] = result["is_valid"]
                emp["email_classification"] = result["classification"]
                emp["confidence_score"] = result["confidence"]

                if result["is_valid"]:
                    verified_count += 1
                    found_valid = True
                    verified_emp = emp
                    company["verification_status"] = "verified"
                    logging.info(f"✅ Valid email found for {full_name}: {candidate}")
                    break

                if verifier.out_of_credits:
                    company["verification_status"] = "skipped_out_of_credit"
                    skipped_count += 1
                    break

                time.sleep(1.0)

            if found_valid or verifier.out_of_credits:
                break

        if not found_valid:
            verified_emp = employees_sorted[0]
            verified_emp.update({
                "verified_email": "",
                "email_verified": False,
                "email_classification": "Unknown",
                "confidence_score": 0.0
            })
            company["verification_status"] = (
                "skipped_out_of_credit" if verifier.out_of_credits else "unverified"
            )

        # Keep only the final chosen employee
        company["employees"] = [verified_emp]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Email verification complete. Saved to {output_file}")
    print(f"\n✅ Email verification complete. {verified_count} verified, {skipped_count} skipped (out of credits).")
    print(f"Results saved to {output_file}")


# =====================
# Entry Point
# =====================
if __name__ == "__main__":
    input_json = "outputs/employees_companies.json"
    output_json = "outputs/employees_email.json"

    print("🚀 Running contact finder with sequential Verifalia accounts...")
    verify_emails_from_json(input_json, output_json)
