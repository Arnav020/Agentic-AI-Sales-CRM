import time
import logging
import base64
import json
from typing import List, Dict
from dataclasses import dataclass
import requests

# =====================
# Logging
# =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# =====================
# Email Verification with Verifalia
# =====================
class VerifaliaVerifier:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.base_url = "https://api.verifalia.com/v2.7"
        self.session = requests.Session()
        
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.session.headers.update({
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json',
            'User-Agent': 'EmailVerifier/1.0'
        })

    def verify_email(self, email: str) -> Dict:
        try:
            validation_data = {"entries": [{"inputData": email}], "quality": "Standard"}
            response = self.session.post(f"{self.base_url}/email-validations", json=validation_data, timeout=30)
            
            if response.status_code == 202:
                job_id = response.json().get("overview", {}).get("id")
                if job_id:
                    return self._wait_for_results(job_id)
            elif response.status_code == 200:
                return self._parse_verification_result(response.json())
            else:
                return self._default_result(email, "api_error")
        except Exception as e:
            logging.error(f"Error verifying email {email}: {e}")
            return self._default_result(email, "exception")

    def _wait_for_results(self, job_id: str, max_attempts: int = 10) -> Dict:
        for _ in range(max_attempts):
            try:
                response = self.session.get(f"{self.base_url}/email-validations/{job_id}", timeout=15)
                if response.status_code == 200:
                    status = response.json().get("overview", {}).get("status")
                    if status == "Completed":
                        return self._parse_verification_result(response.json())
                    time.sleep(2)
            except Exception as e:
                logging.error(f"Error polling job {job_id}: {e}")
                time.sleep(2)
        return self._default_result("", "timeout")

    def _parse_verification_result(self, job_data: Dict) -> Dict:
        try:
            entries = job_data.get("entries", {}).get("data", [])
            if not entries:
                return self._default_result("", "no_entries")
            entry = entries[0]
            classification = entry.get("classification", "Unknown")
            email = entry.get("inputData", "")
            confidence_map = {"Deliverable": 0.95, "Undeliverable": 0.0, "Risky": 0.3, "Unknown": 0.1}
            return {
                "email": email,
                "is_valid": classification == "Deliverable",
                "classification": classification,
                "confidence": confidence_map.get(classification, 0.1),
                "verified": True
            }
        except Exception as e:
            logging.error(f"Error parsing result: {e}")
            return self._default_result("", "parse_error")

    def _default_result(self, email: str, error_type: str) -> Dict:
        return {
            "email": email,
            "is_valid": False,
            "classification": "Unknown",
            "confidence": 0.0,
            "verified": False,
            "error": error_type
        }

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
    all_email_candidates: List[str] = None

# =====================
# Email Permutation Generator
# =====================
class EmailPermutationGenerator:
    @staticmethod
    def generate(name: str, company: str) -> List[str]:
        parts = name.lower().split()
        if len(parts) < 2:
            return []
        first, last = parts[0], parts[-1]
        middle = parts[1] if len(parts) > 2 else ""
        domain = company.lower().replace(" ", "") + ".com"
        patterns = [ 
            f"{first}.{last}@{domain}", # john.doe@company.com 
            f"{first}{last}@{domain}", # johndoe@company.com 
            f"{first}@{domain}", # john@company.com 
            f"{last}.{first}@{domain}", # doe.john@company.com 
            f"{last}{first}@{domain}", # doejohn@company.com 
            f"{first}.{last[0]}@{domain}", # john.d@company.com 
            f"{first}{last[0]}@{domain}", # johnd@company.com 
            f"{first[0]}{last}@{domain}", # jdoe@company.com 
            f"{first[0]}.{last}@{domain}", # j.doe@company.com 
            ]
        if middle:
            patterns += [
                f"{first}.{middle}.{last}@{domain}",
                f"{first[0]}{middle[0]}{last}@{domain}",
            ]
        return list(dict.fromkeys(patterns))

# =====================
# Main Email Verification Logic
# =====================
def verify_emails_from_json(input_file: str, output_file: str, verifalia_user: str, verifalia_pass: str):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    verifier = VerifaliaVerifier(verifalia_user, verifalia_pass)
    
    for company in data:
        for emp in company.get("employees", []):
            email_candidates = EmailPermutationGenerator.generate(emp["name"], company["company"])
            emp_obj = Employee(name=emp["name"], title=emp["title"], company=company["company"],
                               linkedin_url=emp.get("linkedin_url", ""), all_email_candidates=email_candidates)
            
            # Verify in order, stop at first valid email
            for candidate in email_candidates:
                result = verifier.verify_email(candidate)
                if result["is_valid"]:
                    emp_obj.email = candidate
                    emp_obj.verified_email = candidate
                    emp_obj.email_verified = True
                    emp_obj.email_classification = result["classification"]
                    emp_obj.confidence_score = result["confidence"]
                    break  # stop after first valid email
                else:
                    emp_obj.email = candidate
                    emp_obj.email_classification = result["classification"]
                    emp_obj.confidence_score = result["confidence"]

            # Update original dict for JSON output
            emp["email"] = emp_obj.email
            emp["verified_email"] = emp_obj.verified_email
            emp["email_verified"] = emp_obj.email_verified
            emp["email_classification"] = emp_obj.email_classification
            emp["confidence_score"] = emp_obj.confidence_score

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    logging.info(f"✅ Email verification complete. Results saved to {output_file}")

# =====================
# Script Entry
# =====================
if __name__ == "__main__":
    input_json = r".\outputs\employees_companies.json"   # your input JSON
    output_json = r".\outputs\employees_email.json"  # output JSON
    verifalia_username = "pgarg9_be23@thapar.edu"
    verifalia_password = "abcd@1234"
    
    verify_emails_from_json(input_json, output_json, verifalia_username, verifalia_password)
