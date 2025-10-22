"""
Agentic CRM – Email Campaign + Gemini Auto-Reply Agent (Mongo Integrated)
---------------------------------------------------------------------------
• Works inside backend/users/<user_id>/
• Uses backend/utils/generate_token.py for Gmail OAuth
• Loads environment variables from backend/.env
• Reads credentials.json + token.json from backend/
• Saves campaign + reply metadata to MongoDB (collection: email_sender)
• Includes full Gemini-based auto-reply logic
"""

import os
import csv
import json
import time
import base64
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gemini
import google.generativeai as genai

# Local helpers
from backend.utils.generate_token import generate_token
from backend.db.mongo import save_user_output


class CompleteEmailSystem:
    def __init__(self, user_root: str = None):
        self.SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

        # ---- Directories ----
        self.project_root = Path(__file__).resolve().parents[1]  # backend/
        self.user_root = Path(user_root) if user_root else self.project_root
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

        # ---- Gmail Auth ----
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
        self.logger = logging.getLogger(__name__)
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
        return msg

    def send_email(self, recipient: dict):
        msg = self.create_email_message(recipient)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        for attempt in range(3):
            try:
                res = self.service.users().messages().send(userId="me", body={"raw": raw}).execute()
                self._track_email(recipient, "campaign", res.get("id"))
                self.logger.info(f"📤 Sent email → {recipient['email']}")
                return True
            except HttpError as e:
                if getattr(e.resp, "status", None) in (429, 503):
                    delay = 5 * (2 ** attempt)
                    self.logger.warning(f"Rate-limit, retrying in {delay}s…")
                    time.sleep(delay)
                    continue
                self.logger.error(f"Gmail error: {e}")
                break
        return False

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
            self.service.users().messages().modify(userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}).execute()
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
        self.logger.info("🔁 Auto-reply monitor started.")
        try:
            while True:
                msgs = self.get_unread_emails()
                if not msgs:
                    self.logger.info("No unread messages.")
                for m in msgs:
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

                time.sleep(check_interval)
        except KeyboardInterrupt:
            self.logger.info("Auto-reply monitor stopped.")
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
        with self.recipients_csv.open("r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                name, email = r.get("name", "").strip(), r.get("email", "").strip().lower()
                if name and email:
                    recips.append({"name": name, "email": email})
        sent = failed = 0
        for rc in recips:
            ok = self.send_email(rc)
            sent += ok
            failed += not ok
            time.sleep(2)
        self.logger.info(f"Campaign complete — Sent {sent}, Failed {failed}")

        try:
            user_id = self.user_root.name
            save_user_output(
                user_id=user_id, 
                agent="email_sender",
                output_type="campaign_summary",
                data={"sent": sent, "failed": failed, "recipients": recips}
            )
            self.logger.info("Saved campaign summary to user_outputs (mongo)")
        except Exception:
            self.logger.exception("Failed to save campaign summary to user_outputs")

        return sent > 0

    # =========================================================
    # ----------------- Combined Runner -----------------------
    # =========================================================
    def run_complete_system(self):
        self.logger.info(f"🚀 Running full email system ({self.user_root.name})")
        if self.send_bulk_emails():
            self.run_auto_reply_monitoring()
        else:
            self.logger.error("Campaign failed — skipping auto-reply monitor.")


# =============================================================
# ------------------------ Entrypoint -------------------------
# =============================================================
def main(user_folder: str | None = None):
    user_path = Path(user_folder) if user_folder else Path("backend/users/user_demo")
    sys = CompleteEmailSystem(user_root=user_path)
    sys.run_complete_system()


if __name__ == "__main__":
    import sys
    user_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(user_arg)
