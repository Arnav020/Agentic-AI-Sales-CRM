from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

# Gmail API scope - full access
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def generate_token():
    """Generate new Gmail API token"""
    print("🚀 Starting Gmail API authentication...")
    print("📧 Make sure to sign in with: brodomyjob@gmail.com")
    print("-" * 50)

    if not os.path.exists('credentials.json'):
        print("❌ ERROR: credentials.json not found")
        return False

    try:
        # Create OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)

        # Run local server for authentication
        print("🌐 Opening browser for authentication...")
        # Try different ports and methods to avoid redirect URI issues
        try:
            creds = flow.run_local_server(port=8080)
        except:
            try:
                creds = flow.run_local_server(port=8000)
            except:
                # Fallback to console-based auth
                print("⚠️  Local server failed, using console authentication...")
                creds = flow.run_console()

        # Save credentials
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

        print("✅ New Gmail token generated successfully!")
        print("💾 Token saved to token.json")

        # Test the token
        print("🔄 Testing authentication...")
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()

        print(f"✅ Authentication successful!")
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
        print("🚀 Try: python complete_email_system.py")
    else:
        print("\n" + "=" * 60)
        print("❌ FAILED! Token generation unsuccessful")
        print("=" * 60)
        print("🔧 Please check your credentials.json file")
