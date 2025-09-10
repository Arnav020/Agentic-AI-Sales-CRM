import time
import re
import random
import logging
import base64
import json
from typing import List, Optional, Dict
from dataclasses import dataclass
from ddgs import DDGS
from bs4 import BeautifulSoup
import requests

# =====================
# Logging
# =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# =====================
# Email Verification
# =====================
class VerifaliaVerifier:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.base_url = "https://api.verifalia.com/v2.7"
        self.session = requests.Session()
        
        # Set up authentication
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.session.headers.update({
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json',
            'User-Agent': 'EmailFinder/1.0'
        })

    def verify_email(self, email: str) -> Dict:
        """
        Verify a single email address using Verifalia API
        Returns verification results with deliverability status
        """
        try:
            # Submit email validation job
            validation_data = {
                "entries": [{"inputData": email}],
                "quality": "Standard"  # Standard, High, or Extreme
            }
            
            response = self.session.post(
                f"{self.base_url}/email-validations",
                json=validation_data,
                timeout=30
            )
            
            logging.info(f"Verifalia response: {response.status_code} - {response.text[:200]}")
            
            if response.status_code == 202:  # Accepted - job created
                job_data = response.json()
                job_id = job_data.get("overview", {}).get("id")
                
                if job_id:
                    # Poll for results
                    return self._wait_for_results(job_id)
            elif response.status_code == 200:  # Immediate result
                return self._parse_verification_result(response.json())
            elif response.status_code == 401:
                logging.error("Verifalia authentication failed - check credentials")
                return self._default_result(email, "auth_error")
            else:
                logging.error(f"Verifalia API error: {response.status_code} - {response.text}")
                return self._default_result(email, "api_error")
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during email verification: {e}")
            return self._default_result(email, "network_error")
        except Exception as e:
            logging.error(f"Unexpected error during email verification: {e}")
            return self._default_result(email, "unknown_error")

    def _wait_for_results(self, job_id: str, max_attempts: int = 10) -> Dict:
        """Wait for validation job to complete and return results"""
        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}/email-validations/{job_id}",
                    timeout=15
                )
                
                if response.status_code == 200:
                    job_data = response.json()
                    status = job_data.get("overview", {}).get("status")
                    
                    if status == "Completed":
                        return self._parse_verification_result(job_data)
                    elif status in ["InProgress", "Pending"]:
                        time.sleep(2)  # Wait before polling again
                        continue
                    else:
                        logging.error(f"Verification job failed with status: {status}")
                        return self._default_result("", "job_failed")
                else:
                    logging.error(f"Error polling job: {response.status_code}")
                    return self._default_result("", "polling_error")
                
            except requests.exceptions.RequestException as e:
                logging.error(f"Network error while polling: {e}")
                time.sleep(2)
                continue
        
        logging.error("Verification timed out")
        return self._default_result("", "timeout")

    def _parse_verification_result(self, job_data: Dict) -> Dict:
        """Parse Verifalia response and extract relevant information"""
        try:
            entries_obj = job_data.get("entries", {})
            entries_data = entries_obj.get("data", [])
            
            if not entries_data:
                logging.error("No entries data found in response")
                return self._default_result("", "no_entries")
            
            entry = entries_data[0]  # Single email verification
            
            classification = entry.get("classification", "Unknown")
            status = entry.get("status", "Unknown")
            email = entry.get("inputData", "")
            
            logging.info(f"Email: {email}, Classification: {classification}, Status: {status}")
            
            # Map Verifalia classifications to our confidence scores
            confidence_map = {
                "Deliverable": 0.95,
                "Undeliverable": 0.0,
                "Risky": 0.3,
                "Unknown": 0.1
            }
            
            return {
                "email": email,
                "is_valid": classification == "Deliverable",
                "classification": classification,
                "status": status,
                "confidence": confidence_map.get(classification, 0.1),
                "verified": True
            }
            
        except Exception as e:
            logging.error(f"Error parsing verification result: {e}")
            return self._default_result("", "parse_error")

    def _default_result(self, email: str, error_type: str) -> Dict:
        """Return default result when verification fails"""
        return {
            "email": email,
            "is_valid": False,
            "classification": "Unknown",
            "status": f"Error: {error_type}",
            "confidence": 0.0,
            "verified": False
        }

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
    email_verified: bool = False
    email_classification: str = "Unknown"
    verification_status: str = ""
    all_email_candidates: List[str] = None
    verified_email: str = ""

# =====================
# Email Permutation Generator
# =====================
class EmailPermutationGenerator:
    @staticmethod
    def generate_email_permutations(name: str, company: str) -> List[str]:
        """Generate multiple email format permutations for a person's name"""
        name_parts = name.strip().lower().split()
        if len(name_parts) < 2:
            return []
        
        first_name = name_parts[0]
        last_name = name_parts[-1]
        middle_name = name_parts[1] if len(name_parts) > 2 else ""
        
        # Clean company domain
        company_domain = company.lower().replace(' ', '').replace('.', '').replace('-', '') + ".com"
        
        # Common email patterns
        patterns = [
            f"{first_name}.{last_name}@{company_domain}",           # john.doe@company.com
            f"{first_name}{last_name}@{company_domain}",            # johndoe@company.com  
            f"{first_name}@{company_domain}",                       # john@company.com
            f"{last_name}@{company_domain}",                        # doe@company.com
            f"{first_name[0]}.{last_name}@{company_domain}",        # j.doe@company.com
            f"{first_name[0]}{last_name}@{company_domain}",         # jdoe@company.com
            f"{first_name}.{last_name[0]}@{company_domain}",        # john.d@company.com
            f"{first_name}{last_name[0]}@{company_domain}",         # johnd@company.com
            f"{first_name[0]}{last_name[0]}@{company_domain}",      # jd@company.com
            f"{last_name}.{first_name}@{company_domain}",           # doe.john@company.com
            f"{last_name}{first_name}@{company_domain}",            # doejohn@company.com
            f"{last_name}.{first_name[0]}@{company_domain}",        # doe.j@company.com
            f"{last_name}{first_name[0]}@{company_domain}",         # doej@company.com
        ]
        
        # Add middle name variations if available
        if middle_name:
            patterns.extend([
                f"{first_name}.{middle_name}.{last_name}@{company_domain}",     # john.m.doe@company.com
                f"{first_name}{middle_name}{last_name}@{company_domain}",       # johnmdoe@company.com
                f"{first_name[0]}.{middle_name[0]}.{last_name}@{company_domain}", # j.m.doe@company.com
                f"{first_name[0]}{middle_name[0]}{last_name}@{company_domain}",   # jmdoe@company.com
            ])
        
        # Remove duplicates and return
        return list(dict.fromkeys(patterns))

# =====================
# Core Finder
# =====================
class SalesEmployeeFinder:
    def __init__(self, max_employees_per_company: int = 3, search_delay: int = 3, request_timeout: int = 12,
                 verifalia_username: str = None, verifalia_password: str = None):
        self.max_employees = max_employees_per_company
        self.search_delay = search_delay
        self.request_timeout = request_timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        
        # Initialize email verifier if credentials provided
        self.email_verifier = None
        if verifalia_username and verifalia_password:
            self.email_verifier = VerifaliaVerifier(verifalia_username, verifalia_password)
            logging.info("Email verification enabled with Verifalia")

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

        # Verify emails if verifier is available
        if self.email_verifier and employees:
            logging.info("Starting email verification...")
            employees = self._verify_employee_emails(employees)

        return employees[: self.max_employees]

    def _perform_web_search(self, query: str) -> Dict:
        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=10))
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
            body = res.get("body", "")

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
                    # Generate email permutations for this employee
                    email_candidates = EmailPermutationGenerator.generate_email_permutations(name, company_name)
                    default_email = email_candidates[0] if email_candidates else f"{name.split()[0].lower()}.{name.split()[-1].lower()}@{company_name.lower().replace(' ', '')}.com"
                    
                    emp = Employee(
                        name=name,
                        title=role,
                        email=default_email,
                        company=company_name,
                        linkedin_url=url,
                        source="linkedin",
                        confidence_score=0.7,
                        likely_current=True,
                        all_email_candidates=email_candidates
                    )
                    employees.append(emp)
        return employees

    def _is_sales_role(self, job_title: str) -> bool:
        if not job_title:
            return False
        s = job_title.lower()
        keywords = ["sales", "business development", "account executive", "partnership", "growth"]
        return any(k in s for k in keywords)

    def _verify_employee_emails(self, employees: List[Employee]) -> List[Employee]:
        """Verify all employee email permutations using Verifalia and find the working one"""
        verified_employees = []
        
        for i, employee in enumerate(employees):
            logging.info(f"\nVerifying employee {i+1}/{len(employees)}: {employee.name}")
            
            # Get all email candidates for this employee
            email_candidates = employee.all_email_candidates or [employee.email]
            logging.info(f"Testing {len(email_candidates)} email permutations...")
            
            best_result = None
            working_email = None
            
            # Test each email permutation
            for j, candidate_email in enumerate(email_candidates):
                logging.info(f"  Testing {j+1}/{len(email_candidates)}: {candidate_email}")
                
                # Verify this email candidate
                verification_result = self.email_verifier.verify_email(candidate_email)
                
                # If we found a deliverable email, use it and stop testing
                if verification_result.get("is_valid", False):
                    logging.info(f"  ✓ FOUND WORKING EMAIL: {candidate_email}")
                    best_result = verification_result
                    working_email = candidate_email
                    break
                
                # Keep track of the best result so far (prioritize less bad results)
                if best_result is None:
                    best_result = verification_result
                    working_email = candidate_email
                elif (verification_result.get("classification") == "Risky" and
                      best_result.get("classification") == "Undeliverable"):
                    best_result = verification_result
                    working_email = candidate_email
                
                # Rate limiting between verification requests
                if j < len(email_candidates) - 1:
                    time.sleep(0.5)
            
            # Update employee with best verification results
            employee.email = working_email
            employee.verified_email = working_email if best_result.get("is_valid") else ""
            employee.email_verified = best_result.get("verified", False)
            employee.email_classification = best_result.get("classification", "Unknown")
            employee.verification_status = best_result.get("status", "")
            
            # Update confidence score based on verification
            if best_result.get("is_valid", False):
                # Boost confidence significantly for verified emails
                employee.confidence_score = 0.95
                logging.info(f"  ✓ Final result: VERIFIED email {working_email}")
            elif best_result.get("classification") == "Risky":
                # Moderate confidence for risky emails  
                employee.confidence_score = 0.4
                logging.info(f"  ⚠ Final result: RISKY email {working_email}")
            else:
                # Lower confidence for invalid emails
                employee.confidence_score = 0.15
                logging.info(f"  ✗ Final result: UNDELIVERABLE - best attempt was {working_email}")
            
            # Include all employees (even unverified ones with low confidence)
            verified_employees.append(employee)
            
            # Rate limiting between employees
            if i < len(employees) - 1:
                time.sleep(1)
        
        # Sort by confidence score (highest first)
        verified_employees.sort(key=lambda emp: emp.confidence_score, reverse=True)
        return verified_employees

# =====================
# Main
# =====================
def main():
    print("=== Employee Email Finder with Verifalia Verification ===\n")
    
    company_name = input("Enter company name: ").strip()
    
    # Default Verifalia credentials
    verifalia_username = "pgarg9_be23@thapar.edu"
    verifalia_password = "abcd@1234"
    
    print(f"Using Verifalia account: {verifalia_username}")
    
    # Initialize finder with verification enabled
    finder = SalesEmployeeFinder(
        max_employees_per_company=3, 
        search_delay=2,
        verifalia_username=verifalia_username,
        verifalia_password=verifalia_password
    )
    
    employees = finder.search_company_employees(company_name)

    if not employees:
        print(f"\nNo employees found for {company_name}")
    else:
        print(f"\nTop {len(employees)} employees at {company_name}:\n")
        for e in employees:
            verification_info = ""
            if e.email_verified:
                verification_info = f" | ✓ Verified ({e.email_classification})"
            elif e.email_classification != "Unknown":
                verification_info = f" | ✗ {e.email_classification}"
            
            print(f"- {e.name} | {e.title} | {e.email} | {e.linkedin_url}{verification_info} (confidence: {e.confidence_score:.2f})")

if __name__ == "__main__":
    main()