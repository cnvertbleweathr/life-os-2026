import os
import json
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

TOKENS_PATH = "data/running/raw/strava_tokens.json"
OUT_PATH = f"data/running/raw/activities_{datetime.now().strftime('%Y%m%d')}.json"

API_BASE = "https://www.strava.com/api/v3"


def load_tokens():
    if not os.path.exists(TOKENS_PATH):
        raise FileNotFoundError(f"Missing {TOKENS_PATH}. Run scripts/strava_auth.py first.")
    with open(TOKENS_PATH, "r") as f:
        return json.load(f)


def save_tokens(tokens):
    with open(TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


def refresh_access_token(tokens):
    # Strava issues short-lived access tokens and long-lived refresh tokens. :contentReference[oaicite:4]{index=4}
    if tokens.get("expires_at", 0) > int(time.time()) + 60:
        return tokens  # still valid

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    }
    r = requests.post("https://www.strava.com/oauth/token", data=payload)
    r.raise_for_status()
    new_tokens = r.json()
    save_tokens(new_tokens)
    return new_tokens


def fetch_all_activities(access_token, per_page=200, max_pages=10):
    # Activities endpoint supports paging; per_page max is 200. :contentReference[oaicite:5]{index=5}
    activities = []
    headers = {"Authorization": f"Bearer {access_token}"}

    for page in range(1, max_pages + 1):
        params = {"per_page": per_page, "page": page}
        r = requests.get(f"{API_BASE}/athlete/activities", headers=headers, params=params)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        activities.extend(batch)

    return activities


def main():
    tokens = refresh_access_token(load_tokens())
    activities = fetch_all_activities(tokens["access_token"])

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(activities, f, indent=2)

    print(f"Fetched {len(activities)} activities")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

