# backend/agents/agent_runner.py
"""
Agent runner & job-queue.
- Provides per-user job queues with sequential execution.
- Captures logging + stdout/stderr during agent runs and pushes lines into a queue
  which is exposed via SSE by the API.
"""
import importlib
import logging
import queue
import threading
import time
import traceback
import uuid
import sys
from pathlib import Path
from typing import Dict, Any

# In-memory per-process queues. For production use a persistent queue (Redis/Celery).
USER_QUEUES: Dict[str, "queue.Queue"] = {}
USER_WORKER_STARTED: Dict[str, bool] = {}
JOBS: Dict[str, Dict[str, Any]] = {}  # job_id -> job metadata

_lock = threading.Lock()


class QueueLogHandler(logging.Handler):
    """Logging handler that pushes formatted log records into a queue."""

    def __init__(self, q: "queue.Queue"):
        super().__init__(level=logging.INFO)
        self.q = q

    def emit(self, record):
        try:
            msg = self.format(record)
            # push a timestamped line for clarity
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.q.put(f"[{ts}] {msg}")
        except Exception:
            pass


class StreamStdoutToQueue:
    """
    Wraps stdout/stderr to push writes into a queue as well.
    Warning: simple adapter for live logging; flushes don't block agent work much.
    """

    def __init__(self, q: "queue.Queue", stream_name="stdout"):
        self.q = q
        self.stream_name = stream_name
        self._lock = threading.Lock()

    def write(self, data):
        if not data:
            return
        # keep small writes atomic
        with self._lock:
            text = str(data)
            text = text.strip("\n")
            if text:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                self.q.put(f"[{ts}] [{self.stream_name}] {text}")

    def flush(self):
        return


def _ensure_user_queue(user_id: str):
    with _lock:
        if user_id not in USER_QUEUES:
            USER_QUEUES[user_id] = queue.Queue()
            USER_WORKER_STARTED[user_id] = False


def enqueue_job(user_id: str, agent_name: str, user_path: str) -> str:
    """
    Create a job entry and enqueue. Returns job_id.
    """
    _ensure_user_queue(user_id)
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "user_id": user_id,
        "agent": agent_name,
        "user_path": user_path,
        "status": "queued",  # queued | running | completed | failed
        "queue": USER_QUEUES[user_id],  # reference to the queue lines
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "error": None,
    }
    JOBS[job_id] = job
    # enqueue marker (the job meta itself)
    USER_QUEUES[user_id].put(job)
    # ensure worker thread runs for that user
    _start_worker_if_needed(user_id)
    return job_id


def _start_worker_if_needed(user_id: str):
    if USER_WORKER_STARTED.get(user_id):
        return
    t = threading.Thread(target=_user_worker_loop, args=(user_id,), daemon=True)
    USER_WORKER_STARTED[user_id] = True
    t.start()


def _user_worker_loop(user_id: str):
    """
    Worker loop runs jobs one-by-one sequentially from the user's own queue.
    Each queue item is a job dict (as created by enqueue_job).
    """
    q = USER_QUEUES[user_id]
    while True:
        try:
            item = q.get(block=True)  # job dict
            if not isinstance(item, dict):
                # ignore unknown entries
                continue

            job = item
            job_id = job["id"]
            job_meta = JOBS.get(job_id, job)
            job_meta["status"] = "running"
            job_meta["started_at"] = time.time()
            _run_agent_job(job_meta)
            q.task_done()
        except Exception:
            # keep worker alive; log to console as a fallback
            traceback.print_exc()
            time.sleep(1)


def _run_agent_job(job_meta: Dict[str, Any]):
    """
    Executes an agent module main() while capturing logging + stdout/stderr.
    Puts log lines into the user's queue (same object the SSE streams read from).
    When done, sets job_meta['status'] = completed/failed and stores error if any.
    """
    user_id = job_meta["user_id"]
    agent_name = job_meta["agent"]
    user_path = job_meta["user_path"]
    job_id = job_meta["id"]

    q = USER_QUEUES[user_id]

    # push an initial line to indicate start
    q.put(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SYSTEM] Starting job {job_id} → {agent_name}")

    # Attach a logging handler that pushes messages into the queue
    root_logger = logging.getLogger()
    # keep a snapshot of previous handlers to restore later
    previous_handlers = list(root_logger.handlers)
    q_handler = QueueLogHandler(q)
    q_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger.handlers = []  # remove any handlers to avoid duplicates
    root_logger.addHandler(q_handler)
    root_logger.setLevel(logging.INFO)

    # Redirect stdout/stderr to queue stream
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = StreamStdoutToQueue(q, "stdout")
    sys.stderr = StreamStdoutToQueue(q, "stderr")

    job_meta["status"] = "running"
    job_meta["started_at"] = time.time()
    exception_occurred = None
    try:
        # dynamic import & reload to pick runtime changes
        module = importlib.import_module(f"backend.agents.{agent_name}")
        importlib.reload(module)

        # call main appropriately depending on signature
        # Many of your agents define main(user_folder: str | None = None)
        if hasattr(module, "main"):
            try:
                # Call main with user_path as str; agents expecting path string will work
                module.main(user_path)
            except TypeError:
                # fallback: call without args
                module.main()
        else:
            q.put(f"[SYSTEM] Agent {agent_name} has no main() function. Skipping.")
            job_meta["status"] = "failed"
            job_meta["error"] = "no_main"
            return

        job_meta["status"] = "completed"
        job_meta["finished_at"] = time.time()
        q.put(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [SYSTEM] Job {job_id} completed successfully.")
    except Exception as e:
        job_meta["status"] = "failed"
        job_meta["finished_at"] = time.time()
        job_meta["error"] = str(e)
        # log the traceback to queue
        tb = traceback.format_exc()
        q.put(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] {e}")
        for line in tb.splitlines():
            q.put(f"[TRACE] {line}")
        exception_occurred = e
    finally:
        # restore stdout/stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        # restore previous logging handlers
        root_logger.handlers = previous_handlers
        # store meta final state
        JOBS[job_id] = job_meta
        # Put a sentinel to indicate the log stream for this job is done
        q.put(f"__JOB_DONE__::{job_id}::{job_meta['status']}")
        # keep JOBS entry for status queries
