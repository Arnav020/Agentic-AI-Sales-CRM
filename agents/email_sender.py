# agents/email_sender.py
import os
import csv
import json
import time
import base64
import pickle
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
    def __init__(self, requirements_path: str = "inputs/customer_requirements.json"):
        self.SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

        # Project root
        self.project_root = Path(__file__).resolve().parents[1]

        # Setup centralized logging
        self.setup_logging()

        # Load campaign config (customer_requirements.json)
        self.config = self.load_requirements(requirements_path)

        # Read communication settings & template path from config
        self.comm = self.config.get("communication_settings", {})
        self.company = self.config.get("company_profile", {})
        templates = self.config.get("templates", {})
        template_rel = templates.get("initial_email_html")
        if not template_rel:
            self.logger.error("Template path not specified in customer_requirements.json > templates.initial_email_html")
            raise FileNotFoundError("initial_email_html not specified in customer_requirements.json")

        self.template_path = (self.project_root / template_rel).resolve()
        if not self.template_path.exists():
            self.logger.error(f"Template file not found: {self.template_path}")
            raise FileNotFoundError(f"Template file not found: {self.template_path}")

        # Parse template and subject
        self.template_html = self.template_path.read_text(encoding="utf-8")
        self.subject = self._parse_subject_from_template(self.template_html) or f"Hello from {self.company.get('name', '')}".strip()

        # Setup Gmail
        self.service = None
        self.authenticate()

        # Load whitelisted recipients (for testing)
        self.whitelisted_emails = self.load_whitelisted_emails()

        # State: processed emails persisted across restarts
        self.processed_file = self.project_root / "logs" / "processed_emails.json"
        self.processed_emails = self._load_processed_emails()

        # Gemini setup
        load_dotenv()
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not self.GEMINI_API_KEY:
            self.logger.error("GEMINI_API_KEY not found in environment.")
            raise ValueError("GEMINI_API_KEY not found in environment")

        genai.configure(api_key=self.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel("gemini-2.5-flash")
        self.logger.info("Gemini configured with model gemini-2.5-flash")

    # -----------------------
    # Logging
    # -----------------------
    def setup_logging(self):
        logs_dir = (Path(__file__).resolve().parents[1] / "logs")
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / "email_sender.log"

        handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        console = logging.StreamHandler()

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] [PID:%(process)d] %(message)s",
            handlers=[handler, console],
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging initialized — writing to {log_file}")

    # -----------------------
    # Config loading
    # -----------------------
    def load_requirements(self, path: str):
        p = Path(path)
        if not p.exists():
            self.logger.error(f"customer_requirements.json not found at {p}")
            raise FileNotFoundError("customer_requirements.json missing")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # keep existing keys intact (we don't reformat)
            self.logger.info("Loaded customer_requirements.json")
            return data
        except Exception as e:
            self.logger.error(f"Error reading requirements file: {e}")
            raise

    # -----------------------
    # Template utilities
    # -----------------------
    def _parse_subject_from_template(self, html_text: str):
        """
        Optional: allow subject to be declared at the top of template as:
        <!-- SUBJECT: Your subject line here -->
        """
        m = re.search(r"<!--\s*SUBJECT\s*:\s*(.*?)\s*-->", html_text, flags=re.IGNORECASE)
        if m:
            subject = m.group(1).strip()
            self.logger.info(f"Subject parsed from template: {subject}")
            return subject
        return None

    def render_template(self, recipient_name: str, extra_ctx: dict = None):
        """
        Replace placeholders like {{name}}, {{company}}, {{sender_name}}, etc.
        extra_ctx can supply additional variables if required.
        """
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
            rendered = rendered.replace("{{" + k + "}}", str(v))
        return rendered

    # -----------------------
    # Gmail auth
    # -----------------------
    def authenticate(self):
        creds = None
        token_path = Path("token.json")
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
            except Exception as e:
                self.logger.warning(f"Error loading token.json: {e}")

        if not creds or not creds.valid:
            self.logger.warning("Token invalid/missing. Running generate_token()...")
            ok = generate_token()
            if not ok:
                raise RuntimeError("Failed to generate Gmail token.")
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)

        self.service = build("gmail", "v1", credentials=creds)
        self.logger.info("Gmail API authenticated")

    # -----------------------
    # Recipients (testing)
    # -----------------------
    def load_whitelisted_emails(self):
        """
        Load emails from recipients.csv for testing/demo only.
        Assumes recipients.csv has 'name' and 'email' columns.
        """
        p = Path("recipients.csv")
        if not p.exists():
            self.logger.error("recipients.csv not found. Create it for testing recipients.")
            raise FileNotFoundError("recipients.csv missing")
        recipients = set()
        with p.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                email = r.get("email", "").strip().lower()
                if email:
                    recipients.add(email)
        self.logger.info(f"Loaded {len(recipients)} whitelisted/test recipients.")
        return recipients

    # -----------------------
    # Message creation & send
    # -----------------------
    def create_email_message(self, recipient: dict):
        """
        recipient: {'name': 'Foo', 'email': 'foo@example.com'}
        """
        try:
            html_body = self.render_template(recipient['name'])
            # Append dynamic signature based on comm config (keeps signature out of template)
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
            # Include X-Mailer or other helpful headers if desired
            msg.attach(MIMEText(final_html, "html"))
            return msg
        except Exception as e:
            self.logger.error(f"Error creating email message for {recipient.get('email')}: {e}")
            return None

    def send_email(self, recipient: dict, max_retries=3):
        msg_obj = self.create_email_message(recipient)
        if not msg_obj:
            return False
        raw = base64.urlsafe_b64encode(msg_obj.as_bytes()).decode("utf-8")
        body = {"raw": raw}
        attempt = 0
        backoff = 5
        while attempt < max_retries:
            try:
                res = self.service.users().messages().send(userId="me", body=body).execute()
                self._track_email(recipient, kind="campaign", message_id=res.get("id"))
                self.logger.info(f"Sent email to {recipient['email']} (ID: {res.get('id')})")
                return True
            except HttpError as e:
                status = getattr(e.resp, "status", None)
                self.logger.warning(f"Gmail HttpError status={status} attempt={attempt+1}/{max_retries}: {e}")
                if status in (429, 503):
                    time.sleep(backoff)
                    backoff *= 2
                    attempt += 1
                    continue
                else:
                    break
            except Exception as e:
                self.logger.error(f"Unexpected error sending email to {recipient['email']}: {e}")
                break
        self.logger.error(f"Failed to send email to {recipient['email']} after {max_retries} attempts")
        return False

    # -----------------------
    # Tracking
    # -----------------------
    def _track_email(self, recipient: dict, kind: str = "campaign", thread_id: str = "", message_id: str = ""):
        try:
            logs_dir = self.project_root / "logs"
            logs_dir.mkdir(exist_ok=True)
            tracking_file = logs_dir / "email_tracking.csv"
            exists = tracking_file.exists()
            now = datetime.now()
            with tracking_file.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not exists:
                    writer.writerow(["name", "email", "date", "time", "kind", "thread_id", "message_id"])
                writer.writerow([
                    recipient.get("name", ""),
                    recipient.get("email", ""),
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%H:%M:%S"),
                    kind,
                    thread_id or "",
                    message_id or ""
                ])
        except Exception as e:
            self.logger.error(f"Error tracking email: {e}")

    # -----------------------
    # Auto-reply: fetch / detect / details
    # -----------------------
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
            # extract body (prefer text/plain, else try html)
            details["body"] = self._extract_body(m)
            details["id"] = message_id
            return details
        except Exception as e:
            self.logger.error(f"Error fetching message {message_id}: {e}")
            return None

    def _extract_body(self, message):
        payload = message.get("payload", {})
        # recursive helper
        def walk_parts(parts):
            for p in parts:
                mime = p.get("mimeType", "")
                if mime == "text/plain":
                    data = p.get("body", {}).get("data")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8")
                if mime == "text/html":
                    data = p.get("body", {}).get("data")
                    if data:
                        # prefer html if plain not available
                        return base64.urlsafe_b64decode(data).decode("utf-8")
                # nested parts
                if p.get("parts"):
                    res = walk_parts(p.get("parts"))
                    if res:
                        return res
            return None

        if "parts" in payload:
            result = walk_parts(payload["parts"])
            if result:
                return result
        # fallback
        body = payload.get("body", {}).get("data")
        if body:
            return base64.urlsafe_b64decode(body).decode("utf-8")
        return ""

    # -----------------------
    # Classification & reply generation
    # -----------------------
    def classify_email(self, content: str, sender: str):
        auto_indicators = ["out of office", "auto-reply", "automatic reply", "vacation", "noreply", "no-reply"]
        lower = (content or "").lower()
        for i in auto_indicators:
            if i in lower or i in (sender or "").lower():
                return "auto_reply"
        return "reply_needed"

    def _gemini_generate_with_backoff(self, prompt: str, retries: int = 3, initial_backoff: int = 5):
        for attempt in range(retries):
            try:
                response = self.gemini_model.generate_content(prompt, request_options={"timeout": 60})
                if response and getattr(response, "text", None):
                    return response.text.strip()
                raise ValueError("Empty response from Gemini")
            except Exception as e:
                err = str(e).lower()
                # retry on rate-limit / quota-ish messages
                if "429" in err or "quota" in err or "rate-limit" in err or "quota" in err:
                    backoff = initial_backoff * (2 ** attempt)
                    self.logger.warning(f"Gemini rate-limit detected (attempt {attempt+1}/{retries}), backing off {backoff}s")
                    time.sleep(backoff)
                    continue
                self.logger.warning(f"Gemini non-retryable error: {e}")
                break
        return None

    def generate_reply(self, email_data: dict):
        """
        Ask Gemini to create an HTML reply. If Gemini fails, create a fallback reply using sender/company info.
        """
        sender = email_data.get("from", "Contact")
        subject = email_data.get("subject", "")
        body = email_data.get("body", "")

        # Build a prompt that instructs HTML output and includes company context
        prompt = (
            f"You are {self.comm.get('sender_name')} ({self.comm.get('sender_designation')}) at {self.company.get('name')}.\n"
            "You previously sent an outreach email. The contact replied; here is their message:\n\n"
            f"From: {sender}\nSubject: {subject}\n\n{body}\n\n"
            "Generate a concise, professional HTML reply (use <p> for paragraphs). Keep it 2-4 short paragraphs and include a brief signature "
            f"with name, designation and contact email ({self.comm.get('sender_email')}). Do not include subject line or headers — only the HTML body."
        )

        generated = self._gemini_generate_with_backoff(prompt)
        if generated:
            return generated

        # fallback: dynamically generate a polite reply
        fallback = (
            f"<p>Thank you for your response.</p>"
            f"<p>I appreciate you taking the time to reply — I'll review your message and follow up with more details shortly.</p>"
            f"<p>Best regards,<br>{self.comm.get('sender_name')}<br>{self.comm.get('sender_designation')} | {self.company.get('name')}<br>"
            f"<a href='mailto:{self.comm.get('sender_email')}'>{self.comm.get('sender_email')}</a></p>"
        )
        return fallback

    # -----------------------
    # Send reply & marking
    # -----------------------
    def send_reply(self, original_email: dict, reply_html: str):
        try:
            msg = MIMEMultipart("alternative")
            msg["To"] = original_email.get("from")
            # Compose subject as Re: original subject
            base_subject = original_email.get("subject", "")
            msg["Subject"] = f"Re: {base_subject}" if base_subject else f"Re: {self.company.get('name')}"
            # Include in-reply-to header if present
            if original_email.get("message_id"):
                msg["In-Reply-To"] = original_email.get("message_id")
                msg["References"] = original_email.get("message_id")

            msg.attach(MIMEText(reply_html, "html"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            body = {"raw": raw, "threadId": original_email.get("thread_id")}
            sent = self.service.users().messages().send(userId="me", body=body).execute()
            # track reply
            self._track_email({
                "name": original_email.get("from"),
                "email": original_email.get("from")
            }, kind="reply", thread_id=original_email.get("thread_id"), message_id=sent.get("id"))
            self.logger.info(f"Reply sent to {original_email.get('from')} (ID: {sent.get('id')})")
            return True
        except Exception as e:
            self.logger.error(f"Error sending reply: {e}")
            return False

    def mark_as_read(self, message_id: str):
        try:
            self.service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
        except Exception as e:
            self.logger.error(f"Error marking message {message_id} as read: {e}")

    # -----------------------
    # Processed emails persistence
    # -----------------------
    def _load_processed_emails(self):
        try:
            if self.processed_file.exists():
                data = json.loads(self.processed_file.read_text(encoding="utf-8"))
                return set(data)
        except Exception as e:
            self.logger.warning(f"Could not load processed_emails: {e}")
        return set()

    def _save_processed_emails(self):
        try:
            self.processed_file.parent.mkdir(parents=True, exist_ok=True)
            self.processed_file.write_text(json.dumps(list(self.processed_emails)), encoding="utf-8")
        except Exception as e:
            self.logger.error(f"Failed to save processed_emails: {e}")

    # -----------------------
    # Main auto-reply loop
    # -----------------------
    def run_auto_reply_monitoring(self, check_interval: int = 180):
        self.logger.info("Starting auto-reply monitoring loop...")
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
                        sent_ok = self.send_reply(details, reply_html)
                        if sent_ok:
                            self.logger.info("Reply sent; marking as read.")
                    else:
                        self.logger.info(f"No reply needed ({classification})")
                    # mark processed & persist
                    self.mark_as_read(msg_id)
                    self.processed_emails.add(msg_id)
                    self._save_processed_emails()

                self.logger.info(f"Sleeping {check_interval} seconds before next poll...")
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

    # -----------------------
    # Main campaign runner
    # -----------------------
    def send_bulk_emails(self, csv_file: str, rate_limit_delay: int = 2):
        # load recipients (name,email)
        recipients = []
        p = Path(csv_file)
        if not p.exists():
            self.logger.error(f"Recipients CSV not found: {csv_file}")
            return False
        with p.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                name = r.get("name", "").strip()
                email = r.get("email", "").strip().lower()
                if name and email:
                    recipients.append({"name": name, "email": email})

        if not recipients:
            self.logger.error("No valid recipients found in CSV.")
            return False

        sent = failed = 0
        self.logger.info(f"Sending {len(recipients)} emails (delay {rate_limit_delay}s)")
        for i, rc in enumerate(recipients, 1):
            self.logger.info(f"[{i}/{len(recipients)}] -> {rc['email']}")
            ok = self.send_email(rc)
            if ok:
                sent += 1
            else:
                failed += 1
            if i < len(recipients):
                time.sleep(rate_limit_delay)

        self.logger.info(f"Completed campaign. Sent: {sent}, Failed: {failed}")
        return sent > 0

    # -----------------------
    # Run combined system
    # -----------------------
    def run_complete_system(self):
        self.logger.info("Starting complete email system")
        ok = self.send_bulk_emails("recipients.csv", rate_limit_delay=2)
        if not ok:
            self.logger.error("Campaign failed; aborting auto-reply monitoring.")
            return
        self.run_auto_reply_monitoring()

# -----------------------
# Entrypoint
# -----------------------
def main():
    try:
        system = CompleteEmailSystem()
        system.run_complete_system()
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
