#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
youtube_auth_setup.py — One-time local OAuth 2.0 authentication helper.

Run this script locally on your machine to authorize your YouTube channel.
It opens a browser window, completes Google OAuth 2.0 authorization,
and outputs your permanent REFRESH TOKEN for use in .env and GitHub Actions Secrets.

Prerequisites:
1. Go to Google Cloud Console (https://console.cloud.google.com/).
2. Enable "YouTube Data API v3".
3. Under "APIs & Services" -> "OAuth consent screen", select "External", add test user (your Google email).
4. Under "Credentials", click "Create Credentials" -> "OAuth client ID" -> "Desktop App".
5. Download JSON as `client_secrets.json` into this project root, OR enter Client ID & Secret when prompted.
"""

import os
import sys
import json

# Cross-platform UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), "client_secrets.json")
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def update_env_file(client_id: str, client_secret: str, refresh_token: str):
    """Safely updates or appends YouTube OAuth credentials in the local .env file."""
    env_vars = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    env_vars["YOUTUBE_CLIENT_ID"] = client_id
    env_vars["YOUTUBE_CLIENT_SECRET"] = client_secret
    env_vars["YOUTUBE_REFRESH_TOKEN"] = refresh_token

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
    print(f"✅ Updated local .env with YouTube OAuth credentials.")


def main():
    print("=" * 70)
    print("  YouTube Channel OAuth 2.0 Setup (One-Time Token Generator)")
    print("=" * 70)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = None
    client_id = None
    client_secret = None

    if os.path.exists(CLIENT_SECRETS_FILE):
        print(f"📁 Found {CLIENT_SECRETS_FILE}! Loading client configuration...")
        with open(CLIENT_SECRETS_FILE, "r", encoding="utf-8") as f:
            secret_data = json.load(f)
            # Support both 'installed' and 'web' client structures
            client_info = secret_data.get("installed") or secret_data.get("web") or {}
            client_id = client_info.get("client_id")
            client_secret = client_info.get("client_secret")

        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
        )
    else:
        # Check if already present in .env
        env_client_id = ""
        env_client_secret = ""
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("YOUTUBE_CLIENT_ID="):
                        env_client_id = line.split("=", 1)[1].strip()
                    elif line.startswith("YOUTUBE_CLIENT_SECRET="):
                        env_client_secret = line.split("=", 1)[1].strip()

        if env_client_id and env_client_secret:
            print(f"🔑 Loaded Google OAuth credentials directly from .env ({env_client_id[:16]}...)")
            client_id = env_client_id
            client_secret = env_client_secret
        else:
            print("\nℹ️  client_secrets.json not found in root folder.")
            client_id = input("Enter your Google OAuth Client ID: ").strip()
            client_secret = input("Enter your Google OAuth Client Secret: ").strip()

        if not client_id or not client_secret:
            print("❌ Client ID and Secret are required to proceed.")
            sys.exit(1)

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/", "http://127.0.0.1:8080/"],
            }
        }
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=SCOPES,
        )

    import urllib.parse
    from http.server import HTTPServer, BaseHTTPRequestHandler

    flow.redirect_uri = "http://localhost:8080/"
    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )

    with open("AUTH_URL.txt", "w", encoding="utf-8") as f:
        f.write(auth_url)

    print("\n" + "=" * 75, flush=True)
    print("🔗 CLICK OR COPY THIS LINK INTO YOUR BROWSER TO AUTHORIZE:", flush=True)
    print(auth_url, flush=True)
    print("=" * 75 + "\n", flush=True)
    print("⚠️  IMPORTANT: Log in with the Google account that manages your YouTube channel.", flush=True)
    print("   If you see a 'Google hasn't verified this app' warning screen, click 'Advanced' -> 'Go to <app> (unsafe)'.", flush=True)
    print("   Listening on http://localhost:8080/ for authorization response...\n", flush=True)

    auth_code_holder = {}

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                auth_code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                html = """
                <!DOCTYPE html>
                <html>
                <head><title>Authorization Successful</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 60px; background: #0f172a; color: #f8fafc;">
                    <div style="max-width: 520px; margin: 0 auto; background: #1e293b; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); border: 1px solid #334155;">
                        <h1 style="color: #22c55e; margin-bottom: 12px; font-size: 28px;">✅ Authorization Successful!</h1>
                        <p style="font-size: 16px; color: #94a3b8; line-height: 1.6;">Your YouTube Channel OAuth credentials have been authorized and saved.</p>
                        <p style="font-size: 14px; color: #64748b; margin-top: 24px;">You can now safely close this browser tab.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            else:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"No authorization code received.")

        def log_message(self, format, *args):
            pass

    httpd = HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    while "code" not in auth_code_holder:
        httpd.handle_request()
    httpd.server_close()

    auth_code = auth_code_holder["code"]
    flow.fetch_token(code=auth_code)
    refresh_token = flow.credentials.refresh_token

    if not refresh_token:
        print("\n⚠️  No refresh token returned! This happens if consent was already granted.")
        print("   To force Google to generate a new refresh token, revoke app access at:")
        print("   https://myaccount.google.com/permissions and run this script again.")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("🎉 OAuth Authorization Successful!")
    print("=" * 70)
    print("\nHere are your persistent credentials:\n")
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")

    # Save to local .env
    update_env_file(client_id, client_secret, refresh_token)

    # Attempt automatic sync to GitHub Secrets via gh CLI
    try:
        import subprocess
        print("\n🔄 Syncing new YOUTUBE_REFRESH_TOKEN to GitHub Secrets...")
        res = subprocess.run(
            ["gh", "secret", "set", "YOUTUBE_REFRESH_TOKEN", "--body", refresh_token],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            print("✅ Successfully updated YOUTUBE_REFRESH_TOKEN in GitHub Repository Secrets!")
        else:
            print("⚠️  Could not auto-sync to GitHub Secrets via gh CLI. Please update manually if needed.")
    except Exception:
        pass

    print("\n" + "-" * 70)
    print("💡 CRITICAL: To prevent this token from expiring after 7 days:")
    print("1. Go to Google Cloud Console: https://console.cloud.google.com/apis/credentials/consent")
    print("2. Under 'Publishing status', click 'PUBLISH APP' to change status from 'Testing' to 'In production'.")
    print("   (Personal use apps in Production get permanent tokens that never expire!)")
    print("-" * 70)
    print("\nSetup complete! You can now run `py news_pipeline.py` or trigger GitHub Actions.")


if __name__ == "__main__":
    main()
