from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
import os
from dotenv import load_dotenv
from pathlib import Path

# ======================================================
# 🔧 Explicitly load .env from backend directory
# ======================================================
BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
dotenv_path = BASE_DIR / ".env"
load_dotenv(dotenv_path)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError(f"MONGO_URI not found in .env at {dotenv_path}")

# ======================================================
# 🔗 MongoDB Connection
# ======================================================
client = MongoClient(MONGO_URI)
db = client["agentic_crm"]

# ======================================================
# 🧱 User-centric helpers (new structure)
# ======================================================
def save_user_input(user_id: str, input_type: str, data: dict):
    """
    Save a user-scoped input.
    input_type: e.g. 'customer_requirements', 'companies'
    """
    doc = {
        "user_id": user_id,
        "type": input_type,
        "data": data,
        "timestamp": datetime.utcnow()
    }
    db["user_inputs"].insert_one(doc)


def save_user_output(user_id: str, agent: str, output_type: str, data: dict):
    """
    Save a user-scoped output.
    agent: which agent produced it (enrichment_agent, scoring_agent, etc.)
    output_type: e.g. 'enriched_companies', 'lead_scores', 'employees_email'
    """
    doc = {
        "user_id": user_id,
        "agent": agent,
        "output_type": output_type,
        "data": data,
        "timestamp": datetime.utcnow()
    }
    db["user_outputs"].insert_one(doc)


def get_user_inputs(user_id: str, input_type: str = None, limit: int = 50):
    """Retrieve recent user inputs."""
    q = {"user_id": user_id}
    if input_type:
        q["type"] = input_type
    return list(db["user_inputs"].find(q).sort("timestamp", -1).limit(limit))


def get_user_outputs(user_id: str, agent: str = None, output_type: str = None, limit: int = 50):
    """Retrieve recent user outputs."""
    q = {"user_id": user_id}
    if agent:
        q["agent"] = agent
    if output_type:
        q["output_type"] = output_type
    return list(db["user_outputs"].find(q).sort("timestamp", -1).limit(limit))


# ======================================================
# ⚙️ Utilities for migration & index creation
# ======================================================
def ensure_indexes():
    """Create indexes for efficient queries (idempotent)."""
    # user_inputs
    db["user_inputs"].create_index([
        ("user_id", ASCENDING),
        ("type", ASCENDING),
        ("timestamp", DESCENDING)
    ])

    # user_outputs
    db["user_outputs"].create_index([
        ("user_id", ASCENDING),
        ("agent", ASCENDING),
        ("output_type", ASCENDING),
        ("timestamp", DESCENDING)
    ])

    # keep an index on email_sender timestamps for analytics
    db["email_sender"].create_index([
        ("user_id", ASCENDING),
        ("timestamp", DESCENDING)
    ])

    # lead_scores (if present) index
    db["lead_scores"].create_index([
        ("user_id", ASCENDING),
        ("timestamp", DESCENDING)
    ])


def mirror_agent_to_user_outputs(agent_collection: str, agent_field_user_key="user_id"):
    """
    Copy documents from an agent collection into user_outputs.
    One-time use during migration to user-centric schema.
    """
    cursor = db[agent_collection].find({})
    for doc in cursor:
        user_id = doc.get(agent_field_user_key) or doc.get("user") or doc.get("user_id") or "unknown"
        out_type = agent_collection
        payload = {
            k: v for k, v in doc.items()
            if k not in ("_id", "timestamp", agent_field_user_key)
        }
        save_user_output(user_id=str(user_id), agent=agent_collection, output_type=out_type, data=payload)


# ======================================================
# 🚀 Auto-run index setup (safe)
# ======================================================
try:
    ensure_indexes()
except Exception as e:
    print(f"⚠️ Index creation skipped: {e}")
