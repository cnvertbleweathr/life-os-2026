import os
import time
import requests

BASE = "https://pixe.la/v1/users"

PIXELA_USER = os.environ["PIXELA_USER"]
PIXELA_TOKEN = os.environ["PIXELA_TOKEN"]

def _headers():
    return {"X-USER-TOKEN": PIXELA_TOKEN}

def create_graph(graph_id: str, name: str, color: str = "shibafu", timezone: str = "America/Denver"):
    """
    POST /v1/users/<username>/graphs
    """
    url = f"{BASE}/{PIXELA_USER}/graphs"
    payload = {
        "id": graph_id,
        "name": name,
        "unit": "done",
        "type": "int",
        "color": color,
        "timezone": timezone,
    }
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def upsert_pixel(graph_id: str, yyyymmdd: str, quantity: int):
    """
    PUT /v1/users/<username>/graphs/<graphID>/<yyyyMMdd>
    (creates pixel if it doesn't exist)
    """
    url = f"{BASE}/{PIXELA_USER}/graphs/{graph_id}/{yyyymmdd}"
    payload = {"quantity": str(int(quantity))}
    r = requests.put(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def get_pixel(graph_id: str, yyyymmdd: str):
    """
    GET /v1/users/<username>/graphs/<graphID>/<yyyyMMdd>
    """
    url = f"{BASE}/{PIXELA_USER}/graphs/{graph_id}/{yyyymmdd}"
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()  # {"quantity":"1", ...}

def get_pixels_range(graph_id: str, date_from: str, date_to: str):
    """
    GET /v1/users/<username>/graphs/<graphID>/pixels?from=...&to=...&withBody=true
    """
    url = f"{BASE}/{PIXELA_USER}/graphs/{graph_id}/pixels"
    params = {"from": date_from, "to": date_to, "withBody": "true"}
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()  # {"pixels":[{"date":"20260101","quantity":"1"}, ...]}
