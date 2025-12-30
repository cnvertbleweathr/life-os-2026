import os
import json
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8000/callback")

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("Missing STRAVA_CLIENT_ID or STRAVA_CLIENT_SECRET in .env")

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"

# Minimal scopes for reading your activities (private activities may require read_all)
# Start with "read,activity:read" and bump if needed.
SCOPE = "read,activity:read"

TOKENS_PATH = "data/running/raw/strava_tokens.json"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != urlparse(REDIRECT_URI).path:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        error = qs.get("error", [None])[0]

        if error:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Auth error: {error}".encode("utf-8"))
            return

        if not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code")
            return

        # Exchange code for tokens (access + refresh)
        payload = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }
        r = requests.post(TOKEN_URL, data=payload)
        r.raise_for_status()
        tokens = r.json()

        os.makedirs(os.path.dirname(TOKENS_PATH), exist_ok=True)
        with open(TOKENS_PATH, "w") as f:
            json.dump(tokens, f, indent=2)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Strava connected. You can close this tab.")

        # Stop the server after handling one request
        raise SystemExit


def main():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "force",
        "scope": SCOPE,
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    print("Opening:", url)
    webbrowser.open(url)

    host = "localhost"
    port = int(urlparse(REDIRECT_URI).port or 8000)
    print(f"Listening on http://{host}:{port}{urlparse(REDIRECT_URI).path} ...")

    httpd = HTTPServer((host, port), Handler)
    try:
        httpd.serve_forever()
    except SystemExit:
        pass
    finally:
        httpd.server_close()
        print(f"Saved tokens to {TOKENS_PATH}")


if __name__ == "__main__":
    main()

