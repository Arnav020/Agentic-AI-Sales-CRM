# backend/api/routes/analytics.py
from fastapi import APIRouter, HTTPException
from backend.db.mongo import db
from datetime import datetime
from pathlib import Path

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]
USERS_DIR = BASE / "users"


@router.get("/overview/{user_id}")
def analytics_overview(user_id: str):
    """
    Returns unified analytics overview:
    - Counts of user_inputs and user_outputs
    - Aggregated per-agent statistics (from user_outputs)
    - Derived CRM metrics
    """
    if not (USERS_DIR / user_id).exists():
        raise HTTPException(status_code=404, detail="User not found")

    counts = {"user_inputs": 0, "user_outputs": 0}
    try:
        counts["user_inputs"] = db["user_inputs"].count_documents({"user_id": user_id})
        counts["user_outputs"] = db["user_outputs"].count_documents({"user_id": user_id})
    except Exception:
        pass

    # Aggregate per-agent stats
    per_agent = []
    try:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$agent", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        per_agent = list(db["user_outputs"].aggregate(pipeline))
    except Exception:
        per_agent = []

    # Derived CRM metrics based on unified schema
    def count(agent_name: str):
        try:
            return db["user_outputs"].count_documents({"user_id": user_id, "agent": agent_name})
        except Exception:
            return 0

    derived = {
        "total_enrichments": count("enrichment_agent"),
        "total_lead_scores": count("scoring_agent"),
        "employee_searches": count("employee_finder"),
        "contact_verifications": count("contact_finder"),
        "total_campaign_runs": count("email_sender"),
    }

    return {
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat(),
        "counts": {
            "inputs": counts["user_inputs"],
            "outputs": counts["user_outputs"],
            "per_agent": per_agent,
        },
        "derived": derived,
    }


@router.get("/recent/{user_id}")
def analytics_recent(user_id: str, limit: int = 10):
    """
    Fetch recent output events from user_outputs for the given user.
    Includes recent agent runs and campaigns.
    """
    if not (USERS_DIR / user_id).exists():
        raise HTTPException(status_code=404, detail="User not found")

    recent_outputs = []
    try:
        cursor = db["user_outputs"].find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            recent_outputs.append(doc)
    except Exception:
        recent_outputs = []

    return {
        "recent_user_outputs": recent_outputs,
        "legacy_removed": True,
    }
