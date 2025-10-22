# backend/utils/generate_token.py
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
from pathlib import Path

# Gmail API scope - full access
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


def generate_token():
    """Generate new Gmail API token (auto-detects backend path)."""
    print("🚀 Starting Gmail API authentication...")
    print("📧 Make sure to sign in with: brodomyjob@gmail.com")
    print("-" * 50)

    # Dynamically locate backend root (where credentials.json exists)
    backend_root = Path(__file__).resolve().parents[1]
    cred_path = backend_root / "credentials.json"
    token_path = backend_root / "token.json"

    if not cred_path.exists():
        print(f"❌ ERROR: credentials.json not found at {cred_path}")
        return False

    try:
        # Create OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)

        # Run local server for authentication
        print("🌐 Opening browser for authentication...")
        try:
            creds = flow.run_local_server(port=8080)
        except:
            try:
                creds = flow.run_local_server(port=8000)
            except:
                # Fallback to console-based auth
                print("⚠️  Local server failed, using console authentication...")
                creds = flow.run_console()

        # Save credentials to backend/token.json
        with token_path.open("w") as token:
            token.write(creds.to_json())

        print("✅ New Gmail token generated successfully!")
        print(f"💾 Token saved to {token_path}")

        # Test the token immediately
        print("🔄 Testing authentication...")
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()

        print("✅ Authentication successful!")
        print(f"📧 Email: {profile.get('emailAddress')}")
        print(f"📊 Total messages: {profile.get('messagesTotal', 'Unknown')}")
        print(f"📈 Total threads: {profile.get('threadsTotal', 'Unknown')}")

        return True

    except Exception as e:
        print(f"❌ Error during authentication: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🎯 GMAIL TOKEN GENERATOR")
    print("=" * 60)

    success = generate_token()

    if success:
        print("\n" + "=" * 60)
        print("🎉 SUCCESS! Gmail token generated successfully!")
        print("=" * 60)
        print("✅ You can now run your email automation scripts")
        print("🚀 Try: python -m backend.agents.email_sender user_demo")
    else:
        print("\n" + "=" * 60)
        print("❌ FAILED! Token generation unsuccessful")
        print("=" * 60)
        print("🔧 Please check your backend/credentials.json file")
