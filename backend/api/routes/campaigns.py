# backend/api/routes/campaigns.py
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pathlib import Path
from backend.agents.email_sender import CompleteEmailSystem
from backend.db.mongo import mongo_save_result as save_to_mongo
import traceback

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]
USERS_DIR = BASE / "users"


@router.post("/{user_id}/run")
def run_campaign(user_id: str, background: bool = True, bt: BackgroundTasks = None):
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User not found")

    def task_send():
        try:
            system = CompleteEmailSystem(user_root=str(user_path))
            ok = system.send_bulk_emails()
            # write a summary doc to mongo (redundant with agent, but convenient for API)
            save_to_mongo("email_sender", {
                "user_id": user_id,
                "type": "campaign_triggered_via_api",
                "timestamp": system and __import__("datetime").datetime.utcnow(),
                "status": "ok" if ok else "failed",
            })
        except Exception as e:
            save_to_mongo("email_sender", {
                "user_id": user_id,
                "type": "campaign_triggered_via_api",
                "timestamp": __import__("datetime").datetime.utcnow(),
                "status": "error",
                "error": str(e),
                "trace": traceback.format_exc(),
            })

    if background:
        if bt is None:
            task_send()
            return {"status": "started (no BackgroundTasks provided)", "user": user_id}
        bt.add_task(task_send)
        return {"status": "started", "user": user_id}
    else:
        task_send()
        return {"status": "completed (blocking)", "user": user_id}


@router.post("/{user_id}/start_autoreply")
def start_autoreply(user_id: str, bt: BackgroundTasks, check_interval: int = 180):
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User not found")

    def task_monitor():
        system = CompleteEmailSystem(user_root=str(user_path))
        system.run_auto_reply_monitoring(check_interval=check_interval)

    bt.add_task(task_monitor)
    return {"status": "auto-reply monitor started", "user": user_id}
