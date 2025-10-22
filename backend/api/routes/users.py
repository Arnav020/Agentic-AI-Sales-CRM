# backend/api/routes/users.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]  # backend/
USERS_DIR = BASE / "users"


@router.get("/", response_model=List[str])
def list_users():
    if not USERS_DIR.exists():
        raise HTTPException(status_code=500, detail="users/ directory missing in backend/")
    users = [p.name for p in USERS_DIR.iterdir() if p.is_dir()]
    return users


@router.post("/{user_id}/create")
def create_user(user_id: str):
    user_path = USERS_DIR / user_id
    if user_path.exists():
        return {"message": "User already exists", "path": str(user_path)}
    # create canonical folders
    for name in ("inputs", "outputs", "logs", "templates"):
        (user_path / name).mkdir(parents=True, exist_ok=True)
    return {"message": f"User {user_id} created", "path": str(user_path)}


@router.get("/{user_id}/info")
def user_info(user_id: str):
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User not found")
    info = {
        "path": str(user_path),
        "inputs": [p.name for p in (user_path / "inputs").glob("*")],
        "outputs": [p.name for p in (user_path / "outputs").glob("*")],
        "logs": [p.name for p in (user_path / "logs").glob("*")],
    }
    return info
