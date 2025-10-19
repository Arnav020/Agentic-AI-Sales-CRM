# agents/email_sender.py
"""
Agentic CRM - Multi-user Email Sender (Full Version)
-----------------------------------------------------
• Supports per-user directories: users/<user_id>/
• Reads inputs/templates/recipients from that user's folder
• Logs, processed_emails.json, and email_tracking.csv are per-user
• Uses shared Gmail OAuth token (token.json) and credentials.json in root
• Uses shared Gemini API key from .env in root
• Maintains complete auto-reply, Gemini integration, and campaign logic
"""

import os
import csv
import json
import time
import base64
import logging
import re
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Gmail API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gemini AI imports
import google.generativeai as genai

# Local token generator
from utils.generate_token import generate_token


class CompleteEmailSystem:
    def __init__(self, user_root: str = None):
        self.SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

        # Resolve directories
        self.project_root = Path(__file__).resolve().parents[1]
        self.user_root = Path(user_root) if user_root else self.project_root
        self.inputs_dir = self.user_root / "inputs"
        self.logs_dir = self.user_root / "logs"
        self.templates_dir = self.user_root / "templates"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Setup per-user logging
        self.setup_logging()

        # Load user configuration
        req_path = self.inputs_dir / "customer_requirements.json"
        self.config = self.load_requirements(req_path)
        self.comm = self.config.get("communication_settings", {})
        self.company = self.config.get("company_profile", {})

        # Template path from requirements
        templates = self.config.get("templates", {})
        template_rel = templates.get("initial_email_html")
        if not template_rel:
            raise FileNotFoundError("initial_email_html not found in customer_requirements.json")
        self.template_path = (self.user_root / template_rel).resolve()
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template file not found: {self.template_path}")

        # Read and parse template
        self.template_html = self.template_path.read_text(encoding="utf-8")
        self.subject = self._parse_subject_from_template(self.template_html) or f"Hello from {self.company.get('name', '')}".strip()

        # Gmail setup
        self.service = None
        self.authenticate()

        # Recipients
        self.recipients_csv = self.user_root / "recipients.csv"
        self.whitelisted_emails = self.load_whitelisted_emails(self.recipients_csv)

        # Processed emails per user
        self.processed_file = self.logs_dir / "processed_emails.json"
        self.processed_emails = self._load_processed_emails()

        # Gemini setup
        load_dotenv(self.project_root / ".env")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in .env")
        genai.configure(api_key=self.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel("gemini-2.5-flash")
        self.logger.info("Gemini configured (model: gemini-2.5-flash)")

    # ---------------- Logging ----------------
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
        self.logger.info(f"Logging initialized — writing to {log_file}")

    # ---------------- Load config ----------------
    def load_requirements(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"customer_requirements.json not found at {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.logger.info("Loaded customer_requirements.json")
            return data
        except Exception as e:
            self.logger.error(f"Error reading requirements file: {e}")
            raise

    # ---------------- Template ----------------
    def _parse_subject_from_template(self, html_text: str):
        m = re.search(r"<!--\s*SUBJECT\s*:\s*(.*?)\s*-->", html_text, flags=re.IGNORECASE)
        if m:
            subject = m.group(1).strip()
            self.logger.info(f"Subject parsed: {subject}")
            return subject
        return None

    def render_template(self, recipient_name: str, extra_ctx: dict = None):
        ctx = {
            "name": recipient_name,
            "company": self.company.get("name", ""),
            "product_description": self.company.get("description", ""),
            "sender_name": self.comm.get("sender_name", ""),
            "sender_designation": self.comm.get("sender_designation", ""),
            "sender_email": self.comm.get("sender_email", ""),
            "sender_phone": self.comm.get("sender_phone", "")
        }
        if extra_ctx:
            ctx.update(extra_ctx)
        rendered = self.template_html
        for k, v in ctx.items():
            rendered = rendered.replace(f"{{{{{k}}}}}", str(v))
        return rendered

    # ---------------- Gmail Auth ----------------
    def authenticate(self):
        creds = None
        token_path = Path("token.json")
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
            except Exception as e:
                self.logger.warning(f"Error loading token.json: {e}")
        if not creds or not creds.valid:
            self.logger.warning("Token invalid/missing — regenerating")
            if not generate_token():
                raise RuntimeError("Failed to generate Gmail token")
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
        self.service = build("gmail", "v1", credentials=creds)
        self.logger.info("Gmail API authenticated")

    # ---------------- Recipients ----------------
    def load_whitelisted_emails(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"Recipients CSV not found: {path}")
        recipients = set()
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                email = r.get("email", "").strip().lower()
                if email:
                    recipients.add(email)
        self.logger.info(f"Loaded {len(recipients)} recipients from {path}")
        return recipients

    # ---------------- Email creation ----------------
    def create_email_message(self, recipient: dict):
        try:
            html_body = self.render_template(recipient['name'])
            signature_html = (
                f"<br><strong>Best regards,</strong><br>"
                f"{self.comm.get('sender_name','')}<br>"
                f"{self.comm.get('sender_designation','')} | {self.company.get('name','')}<br>"
                f"<a href='mailto:{self.comm.get('sender_email','')}'>{self.comm.get('sender_email','')}</a><br>"
                f"{self.comm.get('sender_phone','')}"
            )
            final_html = f"<div style='font-family:Arial,sans-serif;font-size:11pt;line-height:1.5'>{html_body}{signature_html}</div>"
            msg = MIMEMultipart("alternative")
            msg["From"] = self.comm.get("sender_email")
            msg["To"] = recipient["email"]
            msg["Subject"] = self.subject
            msg.attach(MIMEText(final_html, "html"))
            return msg
        except Exception as e:
            self.logger.error(f"Error creating email for {recipient.get('email')}: {e}")
            return None

    def send_email(self, recipient: dict, max_retries=3):
        msg_obj = self.create_email_message(recipient)
        if not msg_obj:
            return False
        raw = base64.urlsafe_b64encode(msg_obj.as_bytes()).decode("utf-8")
        body = {"raw": raw}
        backoff = 5
        for attempt in range(max_retries):
            try:
                res = self.service.users().messages().send(userId="me", body=body).execute()
                self._track_email(recipient, "campaign", res.get("id"))
                self.logger.info(f"Sent email to {recipient['email']} (ID: {res.get('id')})")
                return True
            except HttpError as e:
                status = getattr(e.resp, "status", None)
                if status in (429, 503):
                    self.logger.warning(f"Gmail rate limit ({status}) — retrying in {backoff}s")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    self.logger.error(f"Gmail API error: {e}")
                    break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                break
        return False

    # ---------------- Tracking ----------------
    def _track_email(self, recipient, kind="campaign", message_id=""):
        tracking_file = self.logs_dir / "email_tracking.csv"
        exists = tracking_file.exists()
        now = datetime.now()
        with tracking_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["name", "email", "date", "time", "kind", "message_id"])
            writer.writerow([
                recipient.get("name", ""), recipient.get("email", ""),
                now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), kind, message_id
            ])

    # ---------------- Auto Reply Logic ----------------
    def get_unread_emails(self):
        try:
            res = self.service.users().messages().list(userId="me", q="is:unread").execute()
            return res.get("messages", [])
        except Exception as e:
            self.logger.error(f"Error listing unread emails: {e}")
            return []

    def get_email_details(self, message_id: str):
        try:
            m = self.service.users().messages().get(userId="me", id=message_id, format="full").execute()
            headers = m.get("payload", {}).get("headers", [])
            details = {}
            for h in headers:
                name = h.get("name", "").lower()
                if name == "from":
                    details["from"] = h.get("value")
                elif name == "subject":
                    details["subject"] = h.get("value")
                elif name == "message-id":
                    details["message_id"] = h.get("value")
            details["thread_id"] = m.get("threadId")
            details["body"] = self._extract_body(m)
            details["id"] = message_id
            return details
        except Exception as e:
            self.logger.error(f"Error fetching message {message_id}: {e}")
            return None

    def _extract_body(self, message):
        payload = message.get("payload", {})
        def walk(parts):
            for p in parts:
                mime = p.get("mimeType", "")
                data = p.get("body", {}).get("data")
                if mime in ("text/plain", "text/html") and data:
                    return base64.urlsafe_b64decode(data).decode("utf-8")
                if p.get("parts"):
                    res = walk(p["parts"])
                    if res:
                        return res
            return ""
        if "parts" in payload:
            return walk(payload["parts"])
        data = payload.get("body", {}).get("data")
        return base64.urlsafe_b64decode(data).decode("utf-8") if data else ""

    def classify_email(self, content, sender):
        auto_indicators = ["out of office", "auto-reply", "automatic reply", "vacation", "noreply", "no-reply"]
        lower = (content or "").lower()
        for i in auto_indicators:
            if i in lower or i in (sender or "").lower():
                return "auto_reply"
        return "reply_needed"

    def _gemini_generate_with_backoff(self, prompt, retries=3, initial_backoff=5):
        for attempt in range(retries):
            try:
                res = self.gemini_model.generate_content(prompt, request_options={"timeout": 60})
                if res and getattr(res, "text", None):
                    return res.text.strip()
                raise ValueError("Empty Gemini response")
            except Exception as e:
                err = str(e).lower()
                if "429" in err or "quota" in err:
                    delay = initial_backoff * (2 ** attempt)
                    self.logger.warning(f"Gemini rate-limit — retrying in {delay}s")
                    time.sleep(delay)
                    continue
                self.logger.error(f"Gemini error: {e}")
                break
        return None

    def generate_reply(self, email_data):
        sender = email_data.get("from", "Contact")
        subject = email_data.get("subject", "")
        body = email_data.get("body", "")
        prompt = (
            f"You are {self.comm.get('sender_name')} ({self.comm.get('sender_designation')}) at {self.company.get('name')}.\n"
            f"The contact replied:\nFrom: {sender}\nSubject: {subject}\n\n{body}\n\n"
            f"Write a professional, concise HTML reply (2–4 short paragraphs)."
        )

        generated = self._gemini_generate_with_backoff(prompt)

        if generated:
            # 🧹 Clean Gemini prefixes/suffixes
            cleaned = re.sub(r"^(`{3,}|'''|```html|'''html)\s*", "", generated.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r"(`{3,}|'''|</?html>|</?body>)\s*$", "", cleaned.strip(), flags=re.IGNORECASE)
            # If model returned plain text accidentally, wrap it in <p>...</p>
            if not bool(re.search(r"<\s*p|<\s*div|<\s*br|<\s*table", cleaned, re.I)):
                cleaned = f"<p>{cleaned}</p>"
            return cleaned

        # fallback generic HTML
        return (
            f"<p>Thank you for your response.</p>"
            f"<p>I appreciate your reply — I’ll review and follow up shortly.</p>"
            f"<p>Best regards,<br>{self.comm.get('sender_name')}<br>{self.comm.get('sender_designation')} | {self.company.get('name')}<br>"
            f"<a href='mailto:{self.comm.get('sender_email')}'>{self.comm.get('sender_email')}</a></p>"
        )


    def send_reply(self, original_email, reply_html):
        try:
            msg = MIMEMultipart("alternative")
            msg["To"] = original_email.get("from")
            base_subject = original_email.get("subject", "")
            msg["Subject"] = f"Re: {base_subject}" if base_subject else f"Re: {self.company.get('name')}"
            if original_email.get("message_id"):
                msg["In-Reply-To"] = original_email["message_id"]
                msg["References"] = original_email["message_id"]
            msg.attach(MIMEText(reply_html, "html"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            body = {"raw": raw, "threadId": original_email.get("thread_id")}
            sent = self.service.users().messages().send(userId="me", body=body).execute()
            self._track_email({"name": original_email.get("from"), "email": original_email.get("from")},
                              kind="reply", message_id=sent.get("id"))
            self.logger.info(f"Reply sent to {original_email.get('from')}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending reply: {e}")
            return False

    def mark_as_read(self, msg_id):
        try:
            self.service.users().messages().modify(userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}).execute()
        except Exception as e:
            self.logger.error(f"Error marking as read: {e}")

    # ---------------- Persistence ----------------
    def _load_processed_emails(self):
        if self.processed_file.exists():
            try:
                return set(json.loads(self.processed_file.read_text(encoding="utf-8")))
            except Exception:
                return set()
        return set()

    def _save_processed_emails(self):
        self.processed_file.write_text(json.dumps(list(self.processed_emails)), encoding="utf-8")

    # ---------------- Auto-Reply Loop ----------------
    def run_auto_reply_monitoring(self, check_interval=180):
        self.logger.info("Starting auto-reply monitoring...")
        try:
            while True:
                messages = self.get_unread_emails()
                if not messages:
                    self.logger.info("No unread emails.")
                for m in messages:
                    msg_id = m.get("id")
                    if not msg_id or msg_id in self.processed_emails:
                        continue
                    details = self.get_email_details(msg_id)
                    if not details:
                        continue
                    sender = details.get("from", "")
                    if not self._is_whitelisted(sender):
                        self.logger.info(f"Skipping non-whitelisted sender: {sender}")
                        self.mark_as_read(msg_id)
                        self.processed_emails.add(msg_id)
                        self._save_processed_emails()
                        continue
                    classification = self.classify_email(details.get("body", ""), sender)
                    if classification == "reply_needed":
                        reply_html = self.generate_reply(details)
                        self.send_reply(details, reply_html)
                    self.mark_as_read(msg_id)
                    self.processed_emails.add(msg_id)
                    self._save_processed_emails()
                time.sleep(check_interval)
        except KeyboardInterrupt:
            self.logger.info("Auto-reply monitoring stopped by user.")
        except Exception as e:
            self.logger.exception(f"Error in auto-reply loop: {e}")

    def _is_whitelisted(self, sender_header: str):
        if not sender_header:
            return False
        if "<" in sender_header:
            email = sender_header.split("<")[1].split(">")[0].strip().lower()
        else:
            email = sender_header.strip().lower()
        return email in self.whitelisted_emails

    # ---------------- Bulk Campaign ----------------
    def send_bulk_emails(self, rate_limit_delay=2):
        recipients = []
        with self.recipients_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                name = r.get("name", "").strip()
                email = r.get("email", "").strip().lower()
                if name and email:
                    recipients.append({"name": name, "email": email})
        sent = failed = 0
        for i, rc in enumerate(recipients, 1):
            ok = self.send_email(rc)
            sent += ok
            failed += not ok
            if i < len(recipients):
                time.sleep(rate_limit_delay)
        self.logger.info(f"Campaign done — Sent: {sent}, Failed: {failed}")
        return sent > 0

    # ---------------- Combined Runner ----------------
    def run_complete_system(self):
        self.logger.info(f"Running email system for user: {self.user_root.name}")
        ok = self.send_bulk_emails(rate_limit_delay=2)
        if ok:
            self.run_auto_reply_monitoring()
        else:
            self.logger.error("Campaign failed; skipping auto-reply monitoring.")


# ---------------- Entrypoint ----------------
def main(user_folder: str | None = None):
    """
    Main entrypoint for CompleteEmailSystem.
    Supports both:
      • Orchestrator import → main("users/user_demo")
      • Standalone CLI → python agents/email_sender.py user_demo
    """
    if user_folder:
        user_path = Path(user_folder)
    else:
        env_user = os.getenv("USER_FOLDER")
        user_path = Path(env_user) if env_user else Path("users/user_demo")

    system = CompleteEmailSystem(user_root=user_path)
    system.run_complete_system()


if __name__ == "__main__":
    import sys
    user_arg = sys.argv[1] if len(sys.argv) >= 2 else None
    if user_arg:
        user_folder = str(Path("users") / user_arg)
    else:
        user_folder = None

    main(user_folder)

