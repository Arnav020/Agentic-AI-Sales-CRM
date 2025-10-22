# backend/api/routes/agents.py
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pathlib import Path
import importlib
import traceback
from typing import Dict, Any

router = APIRouter()
BASE = Path(__file__).resolve().parents[2]  # backend/
AGENTS_DIR = BASE / "agents"
USERS_DIR = BASE / "users"


def _import_agent_module(agent_name: str):
    # Expected module path: backend.agents.<agent_name>
    try:
        module = importlib.import_module(f"backend.agents.{agent_name}")
        importlib.reload(module)
        return module
    except Exception as e:
        raise ImportError(f"Cannot import agent {agent_name}: {e}")


def _run_agent_sync(agent_name: str, user_path: str) -> Dict[str, Any]:
    """Run agent in-process synchronously; capture basic success/failure."""
    try:
        module = _import_agent_module(agent_name)
        if hasattr(module, "main"):
            module.main(user_path)
            return {"ok": True, "message": f"{agent_name} finished"}
        else:
            return {"ok": False, "error": f"{agent_name} has no main()"}
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()}


@router.post("/{user_id}/run/{agent_name}")
def run_agent(user_id: str, agent_name: str, background: bool = True, bt: BackgroundTasks = None):
    """
    Trigger an agent run for a user.
    - background=True ⇒ run asynchronously (recommended)
    - background=False ⇒ run synchronously and return result when done
    """
    user_path = USERS_DIR / user_id
    if not user_path.exists():
        raise HTTPException(status_code=404, detail="User folder not found")

    # basic safety: agent filename must exist
    agent_file = AGENTS_DIR / f"{agent_name}.py"
    if not agent_file.exists():
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")

    if background:
        def task():
            try:
                _run_agent_sync(agent_name, str(user_path))
            except Exception:
                # errors are logged in agent logs; nothing to return here
                pass
        # add to FastAPI background tasks
        if bt is None:
            # fallback: call directly (shouldn't usually happen)
            task()
            return {"status": "started (no BackgroundTasks provided)"}
        bt.add_task(task)
        return {"status": "started", "agent": agent_name, "user": user_id}
    else:
        res = _run_agent_sync(agent_name, str(user_path))
        return res


@router.get("/list")
def list_available_agents():
    # list agent names (strip .py)
    files = [p.name for p in AGENTS_DIR.glob("*.py") if p.is_file()]
    names = sorted([f[:-3] for f in files if not f.startswith("__")])
    return {"agents": names}
