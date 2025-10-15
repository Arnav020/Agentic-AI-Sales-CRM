# pipeline.py
"""
End-to-end Orchestration Pipeline
---------------------------------
This script connects all agents in sequence:
1. EnrichmentAgent  → enriches companies
2. ScoringAgent     → ranks companies
3. SalesEmployeeFinder → finds top sales employees
4. VerifaliaVerifier (ContactFinder) → verifies emails
5. EmailSender      → sends personalized emails from recipients.csv

All intermediate data is stored in /outputs.
"""

import os
import json
import time
import logging

# === Import Agents ===
from agents.enrichment_agent import EnrichmentAgent
from agents.scoring_agent import ScoringAgent
from agents.employee_finder import SalesEmployeeFinder
from agents.contact_finder import VerifaliaVerifier
from email_sender import EmailSender  # <- unchanged, reads recipients.csv

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === Directories ===
INPUTS_DIR = "inputs"
OUTPUTS_DIR = "outputs"

# Ensure folders exist
os.makedirs(OUTPUTS_DIR, exist_ok=True)


# =========================
# 1. Company Enrichment
# =========================
def run_enrichment():
    logging.info("🔍 Running EnrichmentAgent...")
    agent = EnrichmentAgent(model="mistral:latest")

    with open(os.path.join(INPUTS_DIR, "companies.json"), "r", encoding="utf-8") as f:
        companies = json.load(f)

    enriched = []
    for comp in companies:
        logging.info(f"Enriching: {comp['name']}")
        enriched.append(agent.enrich_lead(comp["name"], comp["website"]))
        time.sleep(1)

    enriched_path = os.path.join(OUTPUTS_DIR, "enriched_companies.json")
    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Enrichment complete → {enriched_path}")
    return enriched_path


# =========================
# 2. Scoring and Ranking
# =========================
def run_scoring(enriched_path):
    logging.info("📊 Running ScoringAgent...")
    req_file = os.path.join(INPUTS_DIR, "customer_requirements.json")
    scored_path = os.path.join(OUTPUTS_DIR, "scored_companies.json")

    agent = ScoringAgent(req_file, enriched_path)
    top_companies = agent.rank_companies(top_n=10)

    with open(scored_path, "w", encoding="utf-8") as f:
        json.dump(top_companies, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Scoring complete → {scored_path}")
    return scored_path


# =========================
# 3. Employee Finder
# =========================
def run_employee_finder(scored_path):
    logging.info("👥 Running SalesEmployeeFinder...")
    finder = SalesEmployeeFinder(max_employees_per_company=3, search_delay=2)

    with open(scored_path, "r", encoding="utf-8") as f:
        scored = json.load(f)

    top_companies = scored[:5]
    results = []

    for comp in top_companies:
        name = comp["company"]
        logging.info(f"Finding employees for {name}...")
        employees = finder.search_company_employees(name)
        results.append({
            "company": name,
            "employees": [
                {"name": e.name, "title": e.title, "email": e.email, "linkedin": e.linkedin_url}
                for e in employees
            ]
        })

    emp_path = os.path.join(OUTPUTS_DIR, "employees_companies.json")
    with open(emp_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Employee discovery complete → {emp_path}")
    return emp_path


# =========================
# 4. Contact Verification
# =========================
def run_contact_verification(emp_path):
    logging.info("📬 Running Contact Verification (Verifalia)...")

    # ⚠️ Load credentials from environment or config.json
    cred_path = os.path.join(INPUTS_DIR, "verifalia_credentials.json")
    with open(cred_path, "r", encoding="utf-8") as f:
        creds = json.load(f)

    verifier = VerifaliaVerifier(creds["username"], creds["password"])

    with open(emp_path, "r", encoding="utf-8") as f:
        employees_data = json.load(f)

    verified = []
    for comp in employees_data:
        verified_emps = []
        for emp in comp["employees"]:
            email = emp.get("email", "")
            if not email:
                continue
            result = verifier.verify_email(email)
            emp.update(result)
            verified_emps.append(emp)
            time.sleep(1)
        verified.append({"company": comp["company"], "employees": verified_emps})

    verified_path = os.path.join(OUTPUTS_DIR, "verified_contacts.json")
    with open(verified_path, "w", encoding="utf-8") as f:
        json.dump(verified, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Contact verification complete → {verified_path}")
    return verified_path


# =========================
# 5. Email Sending
# =========================
def run_email_sender():
    logging.info("📧 Running EmailSender...")
    sender = EmailSender()
    sender.send_emails()  # internally reads recipients.csv
    logging.info("✅ Emails sent successfully!")


# =========================
# MAIN PIPELINE
# =========================
def main():
    logging.info("🚀 Starting full AI lead-generation pipeline...")

    enriched_path = run_enrichment()
    scored_path = run_scoring(enriched_path)
    emp_path = run_employee_finder(scored_path)
    verified_path = run_contact_verification(emp_path)
    run_email_sender()

    logging.info("\n🎯 Pipeline complete!")
    logging.info(f"Artifacts saved in '{OUTPUTS_DIR}'")


if __name__ == "__main__":
    main()
