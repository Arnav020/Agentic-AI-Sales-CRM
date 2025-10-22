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
    Returns a unified analytics overview:
    - Counts of user_inputs and user_outputs
    - Aggregated agent statistics
    - Legacy collections (fallback support)
    """
    # ensure user exists
    if not (USERS_DIR / user_id).exists():
        raise HTTPException(status_code=404, detail="User not found")

    collections = db.list_collection_names()
    counts = {}

    # --- New schema ---
    try:
        inputs_count = db["user_inputs"].count_documents({"user_id": user_id})
        outputs_count = db["user_outputs"].count_documents({"user_id": user_id})
        counts["user_inputs"] = inputs_count
        counts["user_outputs"] = outputs_count
    except Exception:
        counts["user_inputs"] = 0
        counts["user_outputs"] = 0

    # --- Per-agent breakdown from user_outputs ---
    per_agent = []
    try:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$agent", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        per_agent = list(db["user_outputs"].aggregate(pipeline))
    except Exception:
        per_agent = []

    # --- Legacy fallback counts (for agents not yet migrated) ---
    legacy_counts = {}
    for c in collections:
        try:
            legacy_counts[c] = db[c].count_documents({"user_id": user_id})
        except Exception:
            legacy_counts[c] = 0

    # --- Derived metrics for Sales CRM ---
    lead_scores = legacy_counts.get("lead_scores", 0)
    campaigns = legacy_counts.get("email_sender", 0)
    enrichments = legacy_counts.get("enrichment_agent", 0)
    employees = legacy_counts.get("employee_finder", 0)
    contacts = legacy_counts.get("contact_finder", 0)

    return {
        "user_id": user_id,
        "timestamp": datetime.utcnow(),
        "counts": {
            "inputs": counts["user_inputs"],
            "outputs": counts["user_outputs"],
            "per_agent": per_agent,
        },
        "legacy_counts": legacy_counts,
        "derived": {
            "total_lead_scores": lead_scores,
            "total_campaign_runs": campaigns,
            "total_enrichments": enrichments,
            "employee_searches": employees,
            "contact_verifications": contacts,
        },
    }


@router.get("/recent/{user_id}")
def analytics_recent(user_id: str, limit: int = 10):
    """
    Fetch recent output events (from user_outputs) for a given user.
    Includes recent campaigns and lead scores for dashboard.
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

    # Legacy fallback for recent email + leads
    recent_email = []
    try:
        cursor2 = db["email_sender"].find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        for d in cursor2:
            d["_id"] = str(d["_id"])
            recent_email.append(d)
    except Exception:
        recent_email = []

    recent_leads = []
    try:
        cursor3 = db["lead_scores"].find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        for d in cursor3:
            d["_id"] = str(d["_id"])
            recent_leads.append(d)
    except Exception:
        recent_leads = []

    return {
        "recent_user_outputs": recent_outputs,
        "recent_email_events": recent_email,
        "recent_lead_scores": recent_leads,
    }
