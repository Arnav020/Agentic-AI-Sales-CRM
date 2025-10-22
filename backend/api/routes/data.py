# backend/api/routes/data.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
from backend.db.mongo import save_user_input  # NEW
import shutil
import json
import logging

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]
USERS_DIR = BASE / "users"


@router.post("/{user_id}/upload_input")
def upload_input(user_id: str, file: UploadFile = File(...)):
    """
    Uploads any input file (e.g., customer_requirements.json, companies.json)
    Saves it both locally under users/<user_id>/inputs and in MongoDB (user_inputs collection).
    """
    user_dir = USERS_DIR / user_id
    user_input_dir = user_dir / "inputs"
    user_input_dir.mkdir(parents=True, exist_ok=True)

    dest = user_input_dir / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Attempt to save to MongoDB if JSON
    if dest.suffix.lower() == ".json":
        try:
            content = json.loads(dest.read_text(encoding="utf-8"))
            input_type = dest.stem  # e.g., "customer_requirements"
            save_user_input(user_id=user_id, input_type=input_type, data=content)
            logging.info(f"✅ Saved {file.filename} to user_inputs (MongoDB).")
        except Exception as e:
            logging.warning(f"⚠️ Could not save {file.filename} to MongoDB: {e}")

    return {"message": "uploaded", "path": str(dest)}


@router.get("/{user_id}/outputs")
def list_outputs(user_id: str):
    """List all output files under users/<user_id>/outputs."""
    out_dir = USERS_DIR / user_id / "outputs"
    if not out_dir.exists():
        raise HTTPException(status_code=404, detail="User not found")
    files = [p.name for p in out_dir.glob("*")]
    return {"outputs": files}


@router.get("/{user_id}/logs")
def list_logs(user_id: str):
    """List all log files under users/<user_id>/logs."""
    log_dir = USERS_DIR / user_id / "logs"
    if not log_dir.exists():
        raise HTTPException(status_code=404, detail="User not found")
    files = [p.name for p in log_dir.glob("*")]
    return {"logs": files}
