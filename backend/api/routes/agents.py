# backend/api/routes/agents.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pathlib import Path
import traceback
import json
import uuid
import time
import os

from backend.agents.agent_runner import enqueue_job, JOBS, USER_QUEUES

# Import auto-reply control helpers (Option A) from the email_sender module
from backend.agents.email_sender import start_auto_reply, stop_auto_reply as email_stop_helper, email_auto_reply_status

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]  # backend/
AGENTS_DIR = BASE / "agents"
USERS_DIR = BASE / "users"

# default pipeline order
PIPELINE_ORDER = [
    "enrichment_agent",
    "scoring_agent",
    "employee_finder",
    "contact_finder",
    "email_sender"
]


@router.get("/list")
def list_available_agents():
    files = [p.name for p in AGENTS_DIR.glob("*.py") if p.is_file()]
    names = sorted([f[:-3] for f in files if not f.startswith("__")])
    return {"agents": names}

@router.post("/{user_id}/run/pipeline")
def run_pipeline(user_id: str, background: bool = True):
    """
    Enqueue the full pipeline (5 agents) in correct order for the given user.
    Returns the list of job_ids in order.
    """
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User folder not found")

    job_ids = []
    for agent_name in PIPELINE_ORDER:
        agent_file = AGENTS_DIR / f"{agent_name}.py"
        if not agent_file.exists():
            raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
        jid = enqueue_job(user_id, agent_name, str(user_path))
        job_ids.append({"agent": agent_name, "job_id": jid})
    return {"status": "pipeline_queued", "jobs": job_ids}


@router.post("/{user_id}/run/{agent_name}")
def run_agent(user_id: str, agent_name: str, background: bool = True, bt: BackgroundTasks = None):
    """
    Enqueue an agent job for the user. Returns a job_id immediately.
    If background is False the call still enqueues and returns job_id.
    """
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User folder not found")

    agent_file = AGENTS_DIR / f"{agent_name}.py"
    if not agent_file.exists():
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")

    job_id = enqueue_job(user_id, agent_name, str(user_path))

    return {"status": "queued", "job_id": job_id, "agent": agent_name, "user": user_id}





@router.get("/{user_id}/job/{job_id}")
def job_status(user_id: str, job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Job does not belong to this user")
    return {
        "job_id": job_id,
        "agent": job.get("agent"),
        "status": job.get("status"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


@router.get("/{user_id}/stream/{job_id}")
def stream_job_logs(user_id: str, job_id: str, request: Request):

    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Job does not belong to this user")

    q = USER_QUEUES.get(user_id)
    if q is None:
        raise HTTPException(status_code=404, detail="No queue for this user")

    sentinel = f"__JOB_DONE__::{job_id}::"

    def event_generator():
        while True:
            # quick disconnect check best-effort
            try:
                # if client disconnected, break (best-effort)
                if request.client is None:
                    pass
            except Exception:
                pass

            try:
                item = q.get(timeout=1.0)
            except Exception:
                # no item but job may be finished
                job_status = JOBS.get(job_id, {}).get("status")
                if job_status in ("completed", "failed"):
                    # send final close event just in case sentinel was missed
                    yield "event: close\ndata: done\n\n"
                    break
                continue

            # Skip job objects (put them back)
            if isinstance(item, dict):
                try:
                    q.put(item)
                except Exception:
                    pass
                continue

            text = str(item)
            # strip only newline characters from ends and treat internal whitespace intact
            text_stripped = text.strip()
            if not text_stripped:
                # skip blank/spam lines (spaces/tabs/newlines)
                continue

            # Send log line
            yield f"data: {text_stripped}\n\n"

            # Sentinel means job finished
            if text_stripped.startswith(sentinel):
                yield "event: close\ndata: done\n\n"
                return

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{user_id}/output/{agent_name}")
def get_agent_output(user_id: str, agent_name: str):
    """
    Fetch the most recent relevant JSON output for a given agent
    from /users/<user_id>/outputs/.
    """
    output_dir = USERS_DIR / user_id / "outputs"
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Outputs folder not found")

    agent_to_file = {
        "enrichment_agent": "enriched_companies.json",
        "scoring_agent": "scored_companies.json",
        "employee_finder": "employees_companies.json",
        "contact_finder": "employees_email.json",
        # changed: campaign summary (json) instead of CSV so frontend can display recipients/content
        "email_sender": "campaign_summary.json",
    }

    filename = agent_to_file.get(agent_name)
    if not filename:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")

    file_path = output_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"No output found for {agent_name}")

    try:
        if file_path.suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ok": True, "source": "file", "output": data}
        elif file_path.suffix == ".csv":
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            return {"ok": True, "source": "csv", "output": lines[:100]}
        else:
            raise HTTPException(status_code=415, detail="Unsupported file type")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading {filename}: {e}")


# ---------------------
# Email control helpers (Option A)
# ---------------------
def _control_dir_for_user(user_id: str) -> Path:
    user_path = USERS_DIR / user_id
    ctrl = user_path / "control"
    try:
        ctrl.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return ctrl


@router.post("/{user_id}/email_sender/auto_reply/start")
def start_email_auto_reply(user_id: str):
    """
    Start the auto-reply loop in a background thread for the given user.
    """
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User folder not found")
    try:
        res = start_auto_reply(str(user_path))
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/email_sender/stop")
def stop_email_sender(user_id: str):
    """
    Stop the auto-reply monitor for a user (signals thread via stop flag).
    """
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User folder not found")

    try:
        res = email_stop_helper(str(user_path))
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/email_sender/status")
def email_sender_status(user_id: str):
    """
    Return running status for auto-reply background thread / flag.
    """
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User folder not found")
    try:
        return email_auto_reply_status(str(user_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
