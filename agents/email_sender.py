import os
import json
import csv
import logging
import base64
import time
import pickle
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

# Gmail API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gemini AI imports
import google.generativeai as genai

class CompleteEmailSystem:
    def __init__(self):
        # Gmail API scope - full access needed for reading and sending
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

        # Setup logging
        self.setup_logging()

        # Initialize Gmail service
        self.service = None
        self.authenticate()

        # Load email template
        self.template = self.load_template()

        # Auto-reply setup
        self.whitelisted_emails = self.load_whitelisted_emails()
        self.processed_emails = set()

        # Configure Gemini API
        load_dotenv()

        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

        if not self.GEMINI_API_KEY:
            raise ValueError("❌ GEMINI_API_KEY not found in .env file")

        # Configure Gemini
        genai.configure(api_key=self.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        self.logger.info("Gemini API configured successfully using brodomyjob@gmail.com key")


    def setup_logging(self):
        """Setup logging configuration and ensure Email Logs folder exists (in project root)"""
        project_root = Path(__file__).resolve().parents[1]
        logs_dir = project_root / "Email Logs"
        logs_dir.mkdir(exist_ok=True)

        log_file = logs_dir / "complete_email_system.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging initialized. Logs saved in: {log_file}")



    def authenticate(self):
        """Authenticate with Gmail API"""
        creds = None

        # Check for existing credentials
        for token_file in ['token.json', 'token.pickle']:
            if os.path.exists(token_file):
                if token_file.endswith('.json'):
                    creds = Credentials.from_authorized_user_file(token_file, self.SCOPES)
                else:
                    with open(token_file, 'rb') as token:
                        creds = pickle.load(token)
                break

        # Get new credentials if needed
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    self.logger.error("credentials.json not found")
                    raise FileNotFoundError("credentials.json not found")

                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)

            # Save credentials
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        try:
            self.service = build('gmail', 'v1', credentials=creds)
            self.logger.info("Gmail API authentication successful")
        except Exception as e:
            self.logger.error(f"Failed to build Gmail service: {e}")
            raise

    def load_template(self):
        """Load email template"""
        return """<div dir="ltr">
<p style="font-family:Arial,sans-serif;font-size:11pt">
<strong>Hi {{name}},</strong>
</p>

<p style="font-family:Arial,sans-serif;font-size:11pt">
I hope this message finds you well.
</p>

<p style="font-family:Arial,sans-serif;font-size:11pt">
I'm reaching out from <strong>EcoCup Solutions</strong>, where we specialize in high-quality, eco-friendly paper cups that businesses like yours rely on daily. Our cups are:
</p>

<ul style="font-family:Arial,sans-serif;font-size:11pt">
<li>🌱 100% food-grade and safe</li>
<li>♻️ Sustainable and recyclable</li>
<li>💰 Cost-effective with bulk order discounts</li>
<li>🎨 Customizable with your branding</li>
</ul>

<p style="font-family:Arial,sans-serif;font-size:11pt">
We currently supply to <strong>cafés, restaurants, corporate offices, and catering companies</strong>, helping them serve beverages in a more sustainable way while reducing costs.
</p>

<p style="font-family:Arial,sans-serif;font-size:11pt">
I'd love to understand your current paper cup needs and explore how we can help you. Would you be open to a quick call next week?
</p>

<p style="font-family:Arial,sans-serif;font-size:11pt">
Looking forward to your reply.
</p>

<p style="font-family:Arial,sans-serif;font-size:11pt">
<strong>Best regards,</strong><br>
Alex Johnson<br>
Sales Manager | EcoCup Solutions<br>
<a href="mailto:alex.johnson@ecocupsolutions.com">alex.johnson@ecocupsolutions.com</a><br>
+1 (555) 123-4567
</p>
</div>"""

    def load_whitelisted_emails(self):
        """Load whitelisted emails from recipients.csv"""
        whitelisted = set()
        try:
            with open('recipients.csv', 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    whitelisted.add(row['email'].lower())
        except FileNotFoundError:
            self.logger.info("recipients.csv not found, creating with default emails...")
            with open('recipients.csv', 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['name', 'email'])
                emails = [
                    ['Nav', 'capitalbawa@gmail.com'],
                    ['Bawa', 'navnoorbawa21@gmail.com'],
                    ['Jorge', 'navnoorhedgefundmanager@gmail.com'],
                    ['Noor', 'navnoorhedgefund@gmail.com'],
                    ['King', 'navnoorbillionaire@gmail.com'],
                    ['Eloit', 'navnoorstartupfounder@gmail.com']
                ]
                writer.writerows(emails)
            return self.load_whitelisted_emails()

        self.logger.info(f"Loaded {len(whitelisted)} whitelisted emails")
        return whitelisted

    def validate_email(self, email):
        """Validate email address format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    def load_recipients(self, csv_file):
        """Load recipients from CSV file"""
        recipients = []

        if not os.path.exists(csv_file):
            self.logger.error(f"Recipients file not found: {csv_file}")
            return recipients

        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                for row_num, row in enumerate(reader, start=2):
                    name = row.get('name', '').strip()
                    email_field = row.get('email', '').strip()

                    if not name or not email_field:
                        continue

                    emails = [email.strip().lower() for email in email_field.split(',')]

                    for email in emails:
                        if email and self.validate_email(email):
                            recipients.append({
                                'name': name,
                                'email': email,
                                'row_num': row_num
                            })

            self.logger.info(f"Loaded {len(recipients)} valid recipients from {csv_file}")
            return recipients

        except Exception as e:
            self.logger.error(f"Error reading CSV file: {e}")
            return []

    def create_email_message(self, recipient):
        """Create email message with template"""
        try:
            msg = MIMEMultipart()
            msg['From'] = 'brodomyjob@gmail.com'
            msg['To'] = recipient['email']
            msg['Subject'] = 'Eco-friendly Paper Cups for Your Business ☕'

            email_body = self.template.replace('{{name}}', recipient['name'])
            msg.attach(MIMEText(email_body, 'html'))

            return msg.as_string()

        except Exception as e:
            self.logger.error(f"Error creating email message for {recipient['email']}: {e}")
            return None

    def send_email(self, recipient):
        """Send individual email"""
        try:
            message = self.create_email_message(recipient)
            if not message:
                return False

            gmail_message = {
                'raw': base64.urlsafe_b64encode(message.encode()).decode()
            }

            result = self.service.users().messages().send(
                userId='me',
                body=gmail_message
            ).execute()

            self.track_email_sent(recipient)
            self.logger.info(f"✓ Email sent successfully to {recipient['email']} (ID: {result['id']})")
            return True

        except HttpError as error:
            self.logger.error(f"✗ Gmail API error sending to {recipient['email']}: {error}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Unexpected error sending to {recipient['email']}: {e}")
            return False

    def track_email_sent(self, recipient):
        """Track sent email in CSV file inside Email Logs folder (in project root)"""
        try:
            project_root = Path(__file__).resolve().parents[1]
            logs_dir = project_root / "Email Logs"
            logs_dir.mkdir(exist_ok=True)

            tracking_file = logs_dir / "email_tracking.csv"
            file_exists = tracking_file.exists()

            now = datetime.now()
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H:%M:%S')

            with open(tracking_file, 'a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(['name', 'email', 'date', 'time'])
                writer.writerow([recipient['name'], recipient['email'], date_str, time_str])

            self.logger.info(f"Tracked email send to {recipient['email']} at {date_str} {time_str}")

        except Exception as e:
            self.logger.error(f"Error tracking email for {recipient['email']}: {e}")



    def send_bulk_emails(self, csv_file, rate_limit_delay=2):
        """Send emails to all recipients"""
        self.logger.info("🚀 Starting bulk email sending process")

        recipients = self.load_recipients(csv_file)
        if not recipients:
            self.logger.error("No valid recipients found")
            return False

        sent_count = 0
        failed_count = 0

        self.logger.info(f"Sending emails to {len(recipients)} recipients...")
        self.logger.info(f"Rate limit: {rate_limit_delay} seconds between emails")

        for i, recipient in enumerate(recipients):
            self.logger.info(f"Processing {i+1}/{len(recipients)}: {recipient['email']}")

            success = self.send_email(recipient)

            if success:
                sent_count += 1
            else:
                failed_count += 1

            if i < len(recipients) - 1:
                time.sleep(rate_limit_delay)

        # Summary
        self.logger.info("=" * 50)
        self.logger.info("BULK EMAIL SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"Total recipients: {len(recipients)}")
        self.logger.info(f"Successfully sent: {sent_count}")
        self.logger.info(f"Failed: {failed_count}")
        self.logger.info(f"Success rate: {(sent_count/len(recipients)*100):.1f}%")
        self.logger.info("=" * 50)

        return sent_count > 0

    # AUTO-REPLY FUNCTIONALITY
    def is_whitelisted_sender(self, sender_email):
        """Check if sender is in our whitelist"""
        if '<' in sender_email:
            sender_email = sender_email.split('<')[1].split('>')[0]
        return sender_email.lower() in self.whitelisted_emails

    def get_unread_emails(self):
        """Get unread emails from whitelisted senders only"""
        try:
            results = self.service.users().messages().list(
                userId='me',
                q='is:unread'
            ).execute()

            messages = results.get('messages', [])
            whitelisted_messages = []

            for message in messages:
                msg = self.service.users().messages().get(
                    userId='me',
                    id=message['id']
                ).execute()

                headers = msg['payload'].get('headers', [])
                sender = None
                for header in headers:
                    if header['name'] == 'From':
                        sender = header['value']
                        break

                if sender and self.is_whitelisted_sender(sender):
                    whitelisted_messages.append(message)
                    self.logger.info(f"Found whitelisted email from: {sender}")
                else:
                    self.logger.info(f"Skipping non-whitelisted email from: {sender}")

            return whitelisted_messages

        except Exception as e:
            self.logger.error(f"Error getting emails: {e}")
            return []

    def get_email_details(self, message_id):
        """Extract email details"""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id
            ).execute()

            headers = message['payload'].get('headers', [])
            email_data = {}

            for header in headers:
                if header['name'] == 'From':
                    email_data['from'] = header['value']
                elif header['name'] == 'Subject':
                    email_data['subject'] = header['value']
                elif header['name'] == 'Message-ID':
                    email_data['message_id'] = header['value']

            email_data['body'] = self.extract_email_body(message)
            email_data['thread_id'] = message['threadId']
            email_data['id'] = message_id

            return email_data

        except Exception as e:
            self.logger.error(f"Error getting email details: {e}")
            return None

    def extract_email_body(self, message):
        """Extract email body text"""
        try:
            payload = message['payload']

            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body']['data']
                        return base64.urlsafe_b64decode(data).decode('utf-8')

            elif payload['mimeType'] == 'text/plain':
                data = payload['body']['data']
                return base64.urlsafe_b64decode(data).decode('utf-8')

            return "Could not extract email body"

        except Exception as e:
            self.logger.error(f"Error extracting body: {e}")
            return "Error extracting email content"

    def classify_email(self, email_content, sender):
        """Classify if email needs reply"""
        lower_content = email_content.lower()
        lower_subject = sender.lower()

        # Skip auto-replies
        auto_reply_indicators = [
            'out of office', 'auto-reply', 'automatic reply',
            'vacation', 'away from office', 'currently unavailable',
            'do not reply', 'noreply', 'no-reply'
        ]

        for indicator in auto_reply_indicators:
            if indicator in lower_content or indicator in lower_subject:
                return "auto_reply"

        return "reply_needed"

    def generate_reply(self, email_data):
        """Generate context-aware reply using Gemini AI"""
        try:
            # Extract relevant information
            sender = email_data.get('from', 'Unknown')
            subject = email_data.get('subject', 'No Subject')
            body = email_data.get('body', '')

            # Create a prompt for Gemini to understand context and generate reply
            prompt = f"""You are Alex Johnson, Sales Manager at EcoCup Solutions, a company that sells eco-friendly paper cups to businesses.

You previously sent an email to a potential client about your eco-friendly paper cups. They have now replied to you.

Here is their email:
---
From: {sender}
Subject: {subject}

{body}
---

Based on their response, generate a professional, context-aware reply email. The reply should:
1. Address their specific questions or concerns if any
2. Show enthusiasm about their interest
3. Provide helpful information or next steps
4. Be friendly and professional
5. Include your signature at the end
6. Keep it concise (3-5 short paragraphs max)

Your signature should be:
Best regards,
Alex Johnson
Sales Manager | EcoCup Solutions
alex.johnson@ecocupsolutions.com
+1 (555) 123-4567

Generate ONLY the email body text. Do not include subject line or email headers."""

            # Generate reply using Gemini
            self.logger.info("Using Gemini AI to generate context-aware reply...")
            response = self.gemini_model.generate_content(prompt)

            if response and response.text:
                generated_reply = response.text.strip()
                self.logger.info(f"Generated reply length: {len(generated_reply)} characters")
                return generated_reply
            else:
                self.logger.warning("Gemini returned empty response, using fallback")
                return self.generate_fallback_reply()

        except Exception as e:
            self.logger.error(f"Error generating reply with Gemini: {e}")
            self.logger.info("Using fallback reply")
            return self.generate_fallback_reply()

    def generate_fallback_reply(self):
        """Generate simple fallback reply if Gemini fails"""
        return """Thank you for your response!

I appreciate your interest in EcoCup Solutions. I'll review your message and get back to you shortly with more details.

Best regards,
Alex Johnson
Sales Manager | EcoCup Solutions
alex.johnson@ecocupsolutions.com
+1 (555) 123-4567"""

    def send_reply(self, original_email, reply_content):
        """Send reply email"""
        try:
            reply_msg = MIMEMultipart()
            reply_msg['To'] = original_email['from']
            reply_msg['Subject'] = f"Re: {original_email['subject']}"
            reply_msg['In-Reply-To'] = original_email.get('message_id', '')

            reply_msg.attach(MIMEText(reply_content, 'plain'))

            raw_message = base64.urlsafe_b64encode(
                reply_msg.as_bytes()
            ).decode('utf-8')

            message_body = {
                'raw': raw_message,
                'threadId': original_email['thread_id']
            }

            sent_message = self.service.users().messages().send(
                userId='me',
                body=message_body
            ).execute()

            self.logger.info(f"✅ Reply sent successfully to {original_email['from']} (ID: {sent_message['id']})")
            return sent_message['id']

        except Exception as e:
            self.logger.error(f"❌ Error sending reply: {e}")
            return None

    def mark_as_read(self, message_id):
        """Mark email as read"""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        except Exception as e:
            self.logger.error(f"Error marking as read: {e}")

    def run_auto_reply_monitoring(self):
        """Main auto-reply loop"""
        self.logger.info("🚀 Starting auto-reply monitoring for whitelisted emails...")
        self.logger.info(f"Monitoring emails from: {', '.join(self.whitelisted_emails)}")

        while True:
            try:
                self.logger.info(f"⏰ Checking for new emails at {time.strftime('%Y-%m-%d %H:%M:%S')}")

                unread_emails = self.get_unread_emails()

                for email in unread_emails:
                    if email['id'] in self.processed_emails:
                        continue

                    email_data = self.get_email_details(email['id'])
                    if not email_data:
                        continue

                    self.logger.info(f"📧 Processing email from: {email_data['from']}")
                    self.logger.info(f"Subject: {email_data['subject']}")

                    if email['id'] in self.processed_emails:
                        self.logger.info("⏭️  Already processed in this session, skipping...")
                        continue

                    classification = self.classify_email(
                        email_data['body'],
                        email_data['from']
                    )
                    self.logger.info(f"📊 Classification: {classification}")

                    if classification == 'reply_needed':
                        reply_content = self.generate_reply(email_data)
                        self.logger.info("💬 Generating thank you reply...")

                        message_id = self.send_reply(email_data, reply_content)

                        if message_id:
                            self.logger.info("✅ Thank you reply sent successfully!")

                        self.mark_as_read(email['id'])
                    else:
                        self.logger.info(f"⏭️  No reply needed ({classification})")

                    self.processed_emails.add(email['id'])

                if not unread_emails:
                    self.logger.info("📭 No new whitelisted emails found")

                self.logger.info("⏳ Waiting 3 minutes before next check...")
                time.sleep(180)

            except KeyboardInterrupt:
                self.logger.info("🛑 Auto-reply monitoring stopped by user")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in auto-reply loop: {e}")
                time.sleep(60)

    def run_complete_system(self):
        """Run the complete email system - send emails then monitor for replies"""
        print("=" * 60)
        print("🚀 COMPLETE EMAIL AUTOMATION SYSTEM")
        print("=" * 60)

        # Step 1: Send bulk emails
        print("📤 STEP 1: Sending emails to recipients...")
        success = self.send_bulk_emails("recipients.csv", rate_limit_delay=2)

        if not success:
            print("❌ Email sending failed. Stopping.")
            return

        print("✅ Email sending completed successfully!")
        print("")

        # Step 2: Start auto-reply monitoring
        print("🔄 STEP 2: Starting auto-reply monitoring...")
        print("Press Ctrl+C to stop the auto-reply system")
        print("-" * 60)

        try:
            self.run_auto_reply_monitoring()
        except KeyboardInterrupt:
            print("\n🛑 Complete email system stopped by user")

def main():
    """Main function"""
    try:
        system = CompleteEmailSystem()
        system.run_complete_system()

    except KeyboardInterrupt:
        print("\n🛑 System interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()