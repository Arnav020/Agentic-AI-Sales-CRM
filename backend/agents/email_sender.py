# backend/agents/email_sender.py
"""
Agentic CRM – Email Campaign + Gemini Auto-Reply Agent (Mongo Integrated)

- main() now sends campaign only and returns (so agent job completes).
- start_auto_reply / stop_auto_reply / email_auto_reply_status helpers
  allow background auto-reply control (safe cross-process via flag + in-process thread map).
"""

import os
import csv
import json
import time
import base64
import logging
import threading
import re
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Gmail API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gemini
import google.generativeai as genai

# Local helpers
from backend.utils.generate_token import generate_token
from backend.db.mongo import save_user_output

# Module-level map of running auto-reply threads:
# key = user_root (string), value = {"thread": Thread, "instance": CompleteEmailSystem}
_AUTO_REPLY_THREADS = {}
_AUTO_REPLY_LOCK = threading.Lock()


class CompleteEmailSystem:
    def __init__(self, user_root: str = None):
        self.SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

        # ---- Directories ----
        self.project_root = Path(__file__).resolve().parents[1]  # backend/
        self.user_root = Path(user_root) if user_root else self.project_root / "users" / "user_demo"
        self.inputs_dir = self.user_root / "inputs"
        self.logs_dir = self.user_root / "logs"
        self.templates_dir = self.user_root / "templates"
        self.outputs_dir = self.user_root / "outputs"
        for d in [self.logs_dir, self.outputs_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # ---- Logging ----
        self.setup_logging()

        # ---- Environment ----
        load_dotenv(self.project_root / ".env")

        # ---- Config ----
        req_path = self.inputs_dir / "customer_requirements.json"
        self.config = self.load_requirements(req_path)
        self.comm = self.config.get("communication_settings", {})
        self.company = self.config.get("company_profile", {})

        # ---- Template ----
        templates = self.config.get("templates", {})
        rel = templates.get("initial_email_html")
        if not rel:
            raise FileNotFoundError("initial_email_html not found in customer_requirements.json")
        self.template_path = (self.user_root / rel).resolve()
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template file not found: {self.template_path}")
        self.template_html = self.template_path.read_text(encoding="utf-8")
        self.subject = (
            self._parse_subject_from_template(self.template_html)
            or f"Hello from {self.company.get('name','')}"
        )

        # ---- Gmail Auth (lazy: authenticate called in __init__ to match prior behavior) ----
        self.service = None
        self.authenticate()

        # ---- Recipients ----
        self.recipients_csv = self.user_root / "recipients.csv"
        self.whitelisted_emails = self.load_whitelisted_emails(self.recipients_csv)

        # ---- Processed tracking ----
        self.processed_file = self.logs_dir / "processed_emails.json"
        self.processed_emails = self._load_processed_emails()

        # ---- Gemini ----
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not self.GEMINI_API_KEY:
            raise ValueError("❌ GEMINI_API_KEY missing in backend/.env")
        genai.configure(api_key=self.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel("gemini-2.5-flash")
        self.logger.info("✅ Gemini configured (gemini-2.5-flash)")

    # =========================================================
    # ---------------------- Logging --------------------------
    # =========================================================
    def setup_logging(self):
        log_file = self.logs_dir / "email_sender.log"
        handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        console = logging.StreamHandler()
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[handler, console],
        )
        # name logger per-user for easier debug
        self.logger = logging.getLogger(f"email_sender_{self.user_root.name}")
        self.logger.info(f"🪶 Logging initialized → {log_file}")

    # =========================================================
    # ------------------- Config Loading ----------------------
    # =========================================================
    def load_requirements(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"customer_requirements.json missing at {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    # =========================================================
    # ------------------ Template Handling --------------------
    # =========================================================
    def _parse_subject_from_template(self, html_text: str):
        m = re.search(r"<!--\s*SUBJECT\s*:\s*(.*?)\s*-->", html_text, flags=re.I)
        return m.group(1).strip() if m else None

    def render_template(self, name: str):
        ctx = {
            "name": name,
            "company": self.company.get("name", ""),
            "product_description": self.company.get("description", ""),
            "sender_name": self.comm.get("sender_name", ""),
            "sender_designation": self.comm.get("sender_designation", ""),
            "sender_email": self.comm.get("sender_email", ""),
            "sender_phone": self.comm.get("sender_phone", ""),
        }
        rendered = self.template_html
        for k, v in ctx.items():
            rendered = rendered.replace(f"{{{{{k}}}}}", str(v))
        return rendered

    # =========================================================
    # --------------------- Gmail Auth ------------------------
    # =========================================================
    def authenticate(self):
        """
        Uses credentials.json + token.json from backend/.
        Regenerates token automatically via generate_token().
        """
        creds = None
        cred_path = self.project_root / "credentials.json"
        token_path = self.project_root / "token.json"

        if not cred_path.exists():
            raise FileNotFoundError(f"❌ Missing credentials.json in {self.project_root}")

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
            except Exception as e:
                self.logger.warning(f"⚠️ Error loading token.json: {e}")

        if not creds or not creds.valid:
            self.logger.warning("🔄 Token missing or invalid — regenerating...")
            if not generate_token():
                raise RuntimeError("❌ Failed to generate Gmail OAuth token.")
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)

        self.service = build("gmail", "v1", credentials=creds)
        self.logger.info("✅ Gmail authenticated successfully")

    # =========================================================
    # ------------------ Recipients ---------------------------
    # =========================================================
    def load_whitelisted_emails(self, csv_path: Path):
        emails = set()
        if csv_path.exists():
            with csv_path.open("r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    email = row.get("email", "").strip().lower()
                    if email:
                        emails.add(email)
        self.logger.info(f"Loaded {len(emails)} whitelisted recipients.")
        return emails

    # =========================================================
    # -------------------- Email Sending ----------------------
    # =========================================================
    def create_email_message(self, recipient: dict):
        html_body = self.render_template(recipient["name"])
        signature = (
            f"<br><strong>Best regards,</strong><br>"
            f"{self.comm.get('sender_name','')}<br>"
            f"{self.comm.get('sender_designation','')} | {self.company.get('name','')}<br>"
            f"<a href='mailto:{self.comm.get('sender_email','')}'>{self.comm.get('sender_email','')}</a><br>"
            f"{self.comm.get('sender_phone','')}"
        )
        final_html = (
            f"<div style='font-family:Arial,sans-serif;font-size:11pt;line-height:1.5'>{html_body}{signature}</div>"
        )
        msg = MIMEMultipart("alternative")
        msg["From"] = self.comm.get("sender_email")
        msg["To"] = recipient["email"]
        msg["Subject"] = self.subject
        msg.attach(MIMEText(final_html, "html"))
        return msg, final_html

    def send_email(self, recipient: dict):
        msg, html = self.create_email_message(recipient)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        for attempt in range(3):
            try:
                res = self.service.users().messages().send(userId="me", body={"raw": raw}).execute()
                self._track_email(recipient, "campaign", res.get("id"))
                self.logger.info(f"📤 Sent email → {recipient['email']}")
                return True, html
            except HttpError as e:
                if getattr(e.resp, "status", None) in (429, 503):
                    delay = 5 * (2 ** attempt)
                    self.logger.warning(f"Rate-limit, retrying in {delay}s…")
                    time.sleep(delay)
                    continue
                self.logger.error(f"Gmail error: {e}")
                break
        return False, None

    # =========================================================
    # ------------------- Tracking ----------------------------
    # =========================================================
    def _track_email(self, recipient, kind="campaign", msg_id=""):
        path = self.logs_dir / "email_tracking.csv"
        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["name", "email", "date", "time", "kind", "message_id"])
            now = datetime.now()
            writer.writerow([
                recipient.get("name", ""),
                recipient.get("email", ""),
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M:%S"),
                kind,
                msg_id,
            ])

    # =========================================================
    # ------------------ Auto-Reply Logic ---------------------
    # =========================================================
    def get_unread_emails(self):
        try:
            res = self.service.users().messages().list(userId="me", q="is:unread").execute()
            return res.get("messages", [])
        except Exception as e:
            self.logger.error(f"Unread fetch error: {e}")
            return []

    def get_email_details(self, msg_id):
        try:
            m = self.service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
            return {
                "id": msg_id,
                "from": headers.get("from", ""),
                "subject": headers.get("subject", ""),
                "message_id": headers.get("message-id", ""),
                "thread_id": m.get("threadId"),
                "body": self._extract_body(m),
            }
        except Exception as e:
            self.logger.error(f"Email detail error: {e}")
            return None

    def _extract_body(self, msg):
        def walk(parts):
            for p in parts:
                mime = p.get("mimeType", "")
                data = p.get("body", {}).get("data")
                if mime in ("text/plain", "text/html") and data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                if p.get("parts"):
                    out = walk(p["parts"])
                    if out:
                        return out
            return ""
        payload = msg.get("payload", {})
        return walk(payload.get("parts", [])) or base64.urlsafe_b64decode(
            payload.get("body", {}).get("data", "").encode() or b""
        ).decode("utf-8", errors="ignore")

    def classify_email(self, content, sender):
        auto_terms = ["out of office", "auto-reply", "automatic reply", "vacation", "noreply", "no-reply"]
        lower = (content or "").lower()
        if any(k in lower for k in auto_terms) or any(k in sender.lower() for k in auto_terms):
            return "auto_reply"
        return "reply_needed"

    def _gemini_generate(self, prompt):
        for attempt in range(3):
            try:
                res = self.gemini_model.generate_content(prompt, request_options={"timeout": 60})
                if res and getattr(res, "text", None):
                    return res.text.strip()
            except Exception as e:
                if "429" in str(e):
                    time.sleep(5 * (2 ** attempt))
                    continue
                self.logger.error(f"Gemini error: {e}")
                break
        return None

    def generate_reply(self, email):
        prompt = (
            f"You are {self.comm.get('sender_name')} ({self.comm.get('sender_designation')}) at {self.company.get('name')}.\n"
            f"The contact replied:\nFrom: {email.get('from')}\nSubject: {email.get('subject')}\n\n"
            f"{email.get('body','')}\n\nWrite a short, polite HTML reply (2–4 paragraphs)."
        )
        res = self._gemini_generate(prompt)
        if not res:
            res = "<p>Thank you for your response. I’ll get back soon.</p>"
        res = re.sub(r"^(`{3,}|'''|```html|'''html)\s*", "", res, flags=re.I)
        res = re.sub(r"(`{3,}|'''|</?html>|</?body>)\s*$", "", res, flags=re.I)
        if not re.search(r"<\s*p|<\s*div|<\s*br", res, re.I):
            res = f"<p>{res}</p>"
        return res

    def send_reply(self, email, reply_html):
        try:
            msg = MIMEMultipart("alternative")
            msg["To"] = email.get("from")
            msg["Subject"] = f"Re: {email.get('subject','') or self.company.get('name')}"
            if email.get("message_id"):
                msg["In-Reply-To"] = email["message_id"]
                msg["References"] = email["message_id"]
            msg.attach(MIMEText(reply_html, "html"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            body = {"raw": raw, "threadId": email.get("thread_id")}
            self.service.users().messages().send(userId="me", body=body).execute()
            self._track_email({"name": email.get("from"), "email": email.get("from")}, "reply", email.get("id"))
            self.logger.info(f"💬 Auto-replied to {email.get('from')}")
            return True
        except Exception as e:
            self.logger.error(f"Reply error: {e}")
            return False

    def mark_as_read(self, msg_id):
        try:
            self.service.users().messages().modify(userId="me", id=msg_id,
                                                  body={"removeLabelIds": ["UNREAD"]}).execute()
        except Exception as e:
            self.logger.error(f"Mark-as-read error: {e}")

    # =========================================================
    # ----------------- Processed Tracking --------------------
    # =========================================================
    def _load_processed_emails(self):
        if self.processed_file.exists():
            try:
                return set(json.loads(self.processed_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        return set()

    def _save_processed_emails(self):
        self.processed_file.write_text(json.dumps(list(self.processed_emails)), encoding="utf-8")

    # =========================================================
    # ----------------- Auto-Reply Loop -----------------------
    # =========================================================
    def run_auto_reply_monitoring(self, check_interval=180):
        """
        Auto-reply monitoring loop (instance method).
        Loop is stoppable by the filesystem stop flag created by stop().
        """
        self.logger.info("🔁 Auto-reply monitor started.")
        try:
            # ensure previous flag is cleared on natural start
            self._clear_stop_flag()

            while not self._should_stop():
                msgs = self.get_unread_emails()
                if not msgs:
                    self.logger.info("No unread messages.")
                for m in msgs:
                    if self._should_stop():
                        self.logger.info("Stop requested — breaking out of email loop.")
                        break

                    msg_id = m.get("id")
                    if not msg_id or msg_id in self.processed_emails:
                        continue
                    email = self.get_email_details(msg_id)
                    if not email:
                        continue
                    sender = email.get("from", "")
                    if not self._is_whitelisted(sender):
                        self.logger.info(f"Skipping non-whitelisted → {sender}")
                        self.mark_as_read(msg_id)
                        self.processed_emails.add(msg_id)
                        self._save_processed_emails()
                        continue
                    mode = self.classify_email(email.get("body", ""), sender)
                    if mode == "reply_needed":
                        reply_html = self.generate_reply(email)
                        self.send_reply(email, reply_html)
                    self.mark_as_read(msg_id)
                    self.processed_emails.add(msg_id)
                    self._save_processed_emails()
                    try:
                        user_id = self.user_root.name if self.user_root else "unknown"
                        save_user_output(
                            user_id=user_id,
                            agent="email_sender",
                            output_type="auto_reply",
                            data={
                                "sender": sender,
                                "subject": email.get("subject"),
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        )
                        self.logger.info(f"Saved auto-reply metadata to user_outputs (user={user_id})")
                    except Exception:
                        self.logger.exception("Failed to save auto-reply metadata to user_outputs")

                # sleep in small slices so stop flag is responsive
                total_wait = check_interval
                slice_sec = 2.0
                elapsed = 0.0
                while elapsed < total_wait:
                    if self._should_stop():
                        break
                    time.sleep(min(slice_sec, total_wait - elapsed))
                    elapsed += slice_sec

            self.logger.info("⛔ Auto-reply loop terminated cleanly.")
        except KeyboardInterrupt:
            self.logger.info("Auto-reply monitor stopped by KeyboardInterrupt.")
        except Exception as e:
            self.logger.exception(f"Monitor loop error: {e}")

    def _is_whitelisted(self, sender):
        if not sender:
            return False
        if "<" in sender:
            sender = sender.split("<")[1].split(">")[0]
        return sender.strip().lower() in self.whitelisted_emails

    # =========================================================
    # ------------------- Campaign Runner ---------------------
    # =========================================================
    def send_bulk_emails(self):
        recips = []
        if not self.recipients_csv.exists():
            self.logger.error(f"No recipients.csv found at {self.recipients_csv}")
            return False

        with self.recipients_csv.open("r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                name, email = r.get("name", "").strip(), r.get("email", "").strip().lower()
                if name and email:
                    recips.append({"name": name, "email": email})
        sent = failed = 0
        # store per-recipient sent info (for output)
        results = []
        for rc in recips:
            ok, html = self.send_email(rc)
            sent += 1 if ok else 0
            failed += 0 if ok else 1
            results.append({
                "name": rc["name"],
                "email": rc["email"],
                "sent": bool(ok),
                "content_html": html or ""
            })
            # small delay between sends
            time.sleep(2)

        self.logger.info(f"Campaign complete — Sent {sent}, Failed {failed}")

        # Save campaign summary locally (outputs) so frontend can fetch it
        summary = {
            "sent": sent,
            "failed": failed,
            "recipients": results,
            "subject": self.subject,
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            summary_path = self.outputs_dir / "campaign_summary.json"
            summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            self.logger.info(f"Saved campaign_summary to {summary_path}")
        except Exception:
            self.logger.exception("Failed to save campaign summary file")

        try:
            user_id = self.user_root.name
            save_user_output(
                user_id=user_id,
                agent="email_sender",
                output_type="campaign_summary",
                data=summary
            )
            self.logger.info("Saved campaign summary to user_outputs (mongo)")
        except Exception:
            self.logger.exception("Failed to save campaign summary to user_outputs")

        return sent > 0

    # =========================================================
    # ----------------- Combined Runner -----------------------
    # =========================================================
    def run_complete_system(self):
        """
        For agent-run usage we only run campaign (so the agent job can complete).
        Auto-reply must be started separately using start_auto_reply().
        """
        self.logger.info(f"🚀 Running campaign for {self.user_root.name}")
        ok = self.send_bulk_emails()
        if not ok:
            self.logger.error("Campaign failed or no recipients found.")
        return ok

    # -------- Control / Stop flag helpers --------
    def _control_dir(self):
        d = self.user_root / "control"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _stop_flag_path(self):
        return self._control_dir() / "stop_auto_reply.txt"

    def _clear_stop_flag(self):
        """Remove stop flag if exists (called on start)."""
        try:
            p = self._stop_flag_path()
            if p.exists():
                p.unlink()
                self.logger.info("🧼 Cleared previous stop flag.")
        except Exception as e:
            self.logger.warning(f"Could not clear stop flag: {e}")

    def _should_stop(self):
        """Return True if stop flag exists."""
        try:
            return self._stop_flag_path().exists()
        except Exception:
            return False

    def stop(self):
        """Create the stop flag (can be called from API)."""
        try:
            self._control_dir().mkdir(parents=True, exist_ok=True)
            self._stop_flag_path().write_text("stop", encoding="utf-8")
            self.logger.info("🛑 Stop flag written. Auto-reply will stop shortly.")
            return True
        except Exception as e:
            self.logger.exception(f"Failed to write stop flag: {e}")
            return False


# -------------------------
# Module-level helpers (Option A)
# -------------------------
def _thread_key(user_root: str) -> str:
    return str(Path(user_root).resolve())


def start_auto_reply(user_root: str):
    """
    Start auto-reply background thread for the given user_root.
    Idempotent: if a thread is already running it returns started=False.
    """
    key = _thread_key(user_root)
    with _AUTO_REPLY_LOCK:
        entry = _AUTO_REPLY_THREADS.get(key)
        if entry and entry.get("thread") and entry["thread"].is_alive():
            return {"ok": True, "started": False, "message": "Auto-reply already running"}

        # create instance (this will authenticate)
        inst = CompleteEmailSystem(user_root=user_root)

        # ensure stop flag is cleared before starting
        inst._clear_stop_flag()

        thr = threading.Thread(target=_auto_reply_thread_target, args=(inst,), daemon=True)
        _AUTO_REPLY_THREADS[key] = {"thread": thr, "instance": inst}
        thr.start()
        return {"ok": True, "started": True, "message": "Auto-reply started in background"}


def _auto_reply_thread_target(instance: CompleteEmailSystem):
    """
    Run the instance loop and clean up mapping when loop exits.
    """
    try:
        instance.run_auto_reply_monitoring()
    except Exception:
        instance.logger.exception("Auto-reply thread crashed")
    finally:
        key = _thread_key(instance.user_root)
        with _AUTO_REPLY_LOCK:
            _AUTO_REPLY_THREADS.pop(key, None)
        instance.logger.info("Auto-reply background thread has exited")


def stop_auto_reply(user_root: str):
    """
    Stop auto-reply for a user. If a background thread is running, call instance.stop() which writes the flag.
    Also write the flag as fallback so other processes recognize it.
    """
    key = _thread_key(user_root)
    try:
        # always write flag (idempotent)
        ctrl = Path(user_root) / "control"
        ctrl.mkdir(parents=True, exist_ok=True)
        (ctrl / "stop_auto_reply.txt").write_text("stop", encoding="utf-8")
    except Exception:
        pass

    with _AUTO_REPLY_LOCK:
        entry = _AUTO_REPLY_THREADS.get(key)
        if entry:
            inst = entry.get("instance")
            try:
                if inst:
                    inst.stop()
            except Exception:
                pass
            return {"ok": True, "message": "Stop requested (thread signalled) (if it was running)"}

    return {"ok": True, "message": "Stop flag written (no running thread detected)"}


def email_auto_reply_status(user_root: str) -> dict:
    """
    Return running=True if a background thread is alive OR stop flag is absent.
    """
    stop_file = Path(user_root) / "control" / "stop_auto_reply.txt"
    running_flag = not stop_file.exists()
    key = _thread_key(user_root)
    with _AUTO_REPLY_LOCK:
        entry = _AUTO_REPLY_THREADS.get(key)
        thread_alive = bool(entry and entry.get("thread") and entry["thread"].is_alive())
    running = thread_alive or running_flag
    return {"ok": True, "running": bool(running), "thread_alive": thread_alive}


# =============================================================
# Entrypoint for running as a standalone agent (campaign-only)
# =============================================================
def main(user_folder: str | None = None):
    user_path = Path(user_folder) if user_folder else Path("backend/users/user_demo")
    sys = CompleteEmailSystem(user_root=user_path)
    # only run campaign & return so agent job completes
    sys.run_complete_system()


if __name__ == "__main__":
    import sys as _sys
    user_arg = _sys.argv[1] if len(_sys.argv) > 1 else None
    main(user_arg)
