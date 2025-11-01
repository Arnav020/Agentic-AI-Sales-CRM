from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
import os
from dotenv import load_dotenv
from pathlib import Path
from passlib.hash import bcrypt

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
# 🧱 User-centric helpers (existing)
# ======================================================
def save_user_input(user_id: str, input_type: str, data: dict):
    """Save a user-scoped input document to MongoDB."""
    doc = {
        "user_id": user_id,
        "type": input_type,
        "data": data,
        "timestamp": datetime.utcnow()
    }
    db["user_inputs"].insert_one(doc)


def save_user_output(user_id: str, agent: str, output_type: str, data: dict):
    """Save a user-scoped output document to MongoDB."""
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
    db["user_inputs"].create_index([
        ("user_id", ASCENDING),
        ("type", ASCENDING),
        ("timestamp", DESCENDING)
    ])
    db["user_outputs"].create_index([
        ("user_id", ASCENDING),
        ("agent", ASCENDING),
        ("output_type", ASCENDING),
        ("timestamp", DESCENDING)
    ])
    db["email_sender"].create_index([
        ("user_id", ASCENDING),
        ("timestamp", DESCENDING)
    ])
    db["lead_scores"].create_index([
        ("user_id", ASCENDING),
        ("timestamp", DESCENDING)
    ])
    db["users"].create_index("username", unique=True)
    db["users"].create_index("email", unique=True)


def mirror_agent_to_user_outputs(agent_collection: str, agent_field_user_key="user_id"):
    """Migration utility to mirror old agent outputs into user_outputs collection."""
    cursor = db[agent_collection].find({})
    for doc in cursor:
        user_id = doc.get(agent_field_user_key) or doc.get("user") or doc.get("user_id") or "unknown"
        out_type = agent_collection
        payload = {
            k: v for k, v in doc.items()
            if k not in ("_id", "timestamp", agent_field_user_key)
        }
        save_user_output(
            user_id=str(user_id),
            agent=agent_collection,
            output_type=out_type,
            data=payload
        )


# ======================================================
# 🧠 New: User Auth Management (username-based)
# ======================================================
USERS_DIR = BASE_DIR / "users"
users_collection = db["users"]

def create_user_in_db(username: str, email: str, password: str):
    """
    Create a new user with:
    - username (used as folder name + Mongo user_id)
    - email
    - hashed password
    """
    if users_collection.find_one({"username": username}):
        return None  # already exists

    password_hash = bcrypt.hash(password)
    new_user = {
        "user_id": username,
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "created_at": datetime.utcnow(),
    }
    users_collection.insert_one(new_user)

    # Create user folder structure
    user_path = USERS_DIR / username
    for sub in ("inputs", "outputs", "logs", "templates"):
        (user_path / sub).mkdir(parents=True, exist_ok=True)

    return new_user


def verify_user_credentials(username: str, password: str):
    """Verify username + password combination."""
    user = users_collection.find_one({"username": username})
    if not user:
        return None
    if bcrypt.verify(password, user["password_hash"]):
        return user
    return None


# ======================================================
# 🚀 Auto-run index setup (safe)
# ======================================================
try:
    ensure_indexes()
except Exception as e:
    print(f"⚠️ Index creation skipped: {e}")
