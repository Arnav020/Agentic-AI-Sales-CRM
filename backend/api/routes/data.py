from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pathlib import Path
from backend.db.mongo import save_user_input
import shutil
import json
import csv
import logging

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]
USERS_DIR = BASE / "users"

@router.post("/{user_id}/upload_companies_csv")
async def upload_companies_csv(user_id: str, file: UploadFile = File(...)):
    """
    Upload a CSV file (name, website) → convert to companies.json
    and save both locally and in MongoDB.
    """
    user_input_dir = USERS_DIR / user_id / "inputs"
    user_input_dir.mkdir(parents=True, exist_ok=True)

    csv_path = user_input_dir / file.filename
    with csv_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    json_path = user_input_dir / "companies.json"
    companies = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                name = row.get("name") or row.get("Name")
                website = row.get("website") or row.get("Website")
                if name and website:
                    companies.append({"name": name.strip(), "website": website.strip()})
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(companies, jf, indent=2)
        save_user_input(user_id, "companies", companies)
    except Exception as e:
        logging.error(f"Error processing CSV: {e}")
        raise HTTPException(status_code=500, detail="Failed to process CSV")

    return {"message": "✅ companies.json saved", "path": str(json_path), "count": len(companies)}

@router.post("/{user_id}/save_customer_requirements")
async def save_customer_requirements(
    user_id: str,
    requirements_json: str = Form(...),
    template_file: UploadFile = File(None)
):
    """
    Save customer requirements JSON (form input) and optional HTML template file.
    """
    user_input_dir = USERS_DIR / user_id / "inputs"
    user_templates_dir = USERS_DIR / user_id / "templates"
    user_input_dir.mkdir(parents=True, exist_ok=True)
    user_templates_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = json.loads(requirements_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    # Save uploaded HTML template
    if template_file:
        template_path = user_templates_dir / template_file.filename
        with template_path.open("wb") as f:
            shutil.copyfileobj(template_file.file, f)
        data["templates"] = {"initial_email_html": f"templates/{template_file.filename}"}

    json_path = user_input_dir / "customer_requirements.json"
    with json_path.open("w", encoding="utf-8") as jf:
        json.dump(data, jf, indent=2)

    save_user_input(user_id, "customer_requirements", data)

    return {"message": "✅ customer_requirements.json saved", "path": str(json_path)}
