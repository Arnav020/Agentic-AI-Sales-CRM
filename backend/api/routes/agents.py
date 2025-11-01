from fastapi import APIRouter, BackgroundTasks, HTTPException
from pathlib import Path
import importlib
import traceback
import json
from typing import Dict, Any

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]
AGENTS_DIR = BASE / "agents"
USERS_DIR = BASE / "users"


def _import_agent_module(agent_name: str):
    try:
        module = importlib.import_module(f"backend.agents.{agent_name}")
        importlib.reload(module)
        return module
    except Exception as e:
        raise ImportError(f"Cannot import agent {agent_name}: {e}")


def _run_agent_sync(agent_name: str, user_path: str) -> Dict[str, Any]:
    """Run agent synchronously, capturing basic success/failure."""
    try:
        module = _import_agent_module(agent_name)
        if hasattr(module, "main"):
            module.main(user_path)
            return {"ok": True, "message": f"{agent_name} finished successfully"}
        else:
            return {"ok": False, "error": f"{agent_name} has no main()"}
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()}


@router.post("/{user_id}/run/{agent_name}")
def run_agent(user_id: str, agent_name: str, background: bool = True, bt: BackgroundTasks = None):
    """Trigger an agent run for a user (background recommended)."""
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User folder not found")

    agent_file = AGENTS_DIR / f"{agent_name}.py"
    if not agent_file.exists():
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")

    if background:
        def task():
            try:
                _run_agent_sync(agent_name, str(user_path))
            except Exception:
                pass

        if bt is None:
            task()
            return {"status": "started (no BackgroundTasks provided)"}
        bt.add_task(task)
        return {"status": "started", "agent": agent_name, "user": user_id}
    else:
        res = _run_agent_sync(agent_name, str(user_path))
        return res


@router.get("/list")
def list_available_agents():
    files = [p.name for p in AGENTS_DIR.glob("*.py") if p.is_file()]
    names = sorted([f[:-3] for f in files if not f.startswith("__")])
    return {"agents": names}


@router.get("/{user_id}/output/{agent_name}")
def get_agent_output(user_id: str, agent_name: str):
    """
    Fetch the most recent relevant JSON output for a given agent
    from /users/<user_id>/outputs/.
    """
    output_dir = USERS_DIR / user_id / "outputs"
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Outputs folder not found")

    # Map each agent to its corresponding output filename
    agent_to_file = {
        "enrichment_agent": "enriched_companies.json",
        "scoring_agent": "scored_companies.json",
        "employee_finder": "employees_companies.json",
        "contact_finder": "employees_email.json",
        "email_sender": "recipients.csv",  # or summary.json if applicable
    }

    filename = agent_to_file.get(agent_name)
    if not filename:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")

    file_path = output_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"No output found for {agent_name}")

    try:
        # handle JSON outputs
        if file_path.suffix == ".json":
            import json
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ok": True, "source": "file", "output": data}

        # handle CSV outputs gracefully
        elif file_path.suffix == ".csv":
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            return {"ok": True, "source": "csv", "output": lines[:100]}  # limit to preview

        else:
            raise HTTPException(status_code=415, detail="Unsupported file type")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading {filename}: {e}")


