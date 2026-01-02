#!/usr/bin/env python3
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
load_dotenv()

import time
import random

BASE = "https://pixe.la/v1/users"


class PixelaError(RuntimeError):
    pass


@dataclass
class PixelaClient:
    username: str
    token: str
    base_url: str = BASE

    @classmethod
    def from_env(cls) -> "PixelaClient":
        """
        Reads credentials from environment variables.
        Supports both:
          - PIXELA_USERNAME (preferred)
          - PIXELA_USER (back-compat)
        """
        username = os.getenv("PIXELA_USERNAME") or os.getenv("PIXELA_USER")
        token = os.getenv("PIXELA_TOKEN")
        if not username:
            raise PixelaError("Missing PIXELA_USERNAME (or PIXELA_USER) in environment.")
        if not token:
            raise PixelaError("Missing PIXELA_TOKEN in environment.")
        return cls(username=username, token=token)

    def _headers(self) -> Dict[str, str]:
        return {"X-USER-TOKEN": self.token}

    def _handle(self, r: requests.Response) -> Dict[str, Any]:
        """
        Pixela returns JSON with {isSuccess, message}.
        We rely on HTTP status codes, but also surface Pixela message on failure.
        """
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}

        if not r.ok:
            msg = ""
            if isinstance(data, dict):
                msg = data.get("message") or data.get("raw") or ""

            raise PixelaError(f"Pixela HTTP {r.status_code}: {msg}".strip())

        return data if isinstance(data, dict) else {"data": data}

    def _request(self, method: str, url: str, *, json_body: Optional[dict] = None, params: Optional[dict] = None,
                 retries: int = 6, base_sleep: float = 0.4) -> Dict[str, Any]:
        """
        Pixela may intentionally reject some requests (503) for non-supporters.
        This wrapper retries transient failures with exponential backoff + jitter.
        """
        last_err: Optional[Exception] = None

        for attempt in range(retries + 1):
            try:
                r = requests.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                    timeout=30,
                )
                # Retry on transient server errors / throttling
                if r.status_code in (429, 500, 502, 503, 504):
                    # try to capture message for debugging, but don't fail yet
                    try:
                        msg = (r.json() or {}).get("message", "")
                    except Exception:
                        msg = r.text[:200]

                    # If we've exhausted retries, raise
                    if attempt >= retries:
                        raise PixelaError(f"Pixela HTTP {r.status_code}: {msg}".strip())

                    # Exponential backoff + jitter
                    sleep_s = base_sleep * (2 ** attempt) + random.uniform(0, 0.25)
                    time.sleep(sleep_s)
                    continue

                return self._handle(r)

            except Exception as e:
                last_err = e
                if attempt >= retries:
                    raise
                sleep_s = base_sleep * (2 ** attempt) + random.uniform(0, 0.25)
                time.sleep(sleep_s)

        # Should never get here
        raise PixelaError(f"Pixela request failed: {last_err}")


    # --------------------------
    # Graphs
    # --------------------------
    def create_graph(
        self,
        graph_id: str,
        name: str,
        unit: str = "did",
        graph_type: str = "int",
        color: str = "shibafu",
        timezone: str = "America/Denver",
    ) -> Dict[str, Any]:
        """
        POST /v1/users/<username>/graphs
        """
        url = f"{self.base_url}/{self.username}/graphs"
        payload = {
            "id": graph_id,
            "name": name,
            "unit": unit,
            "type": graph_type,
            "color": color,
            "timezone": timezone,
        }
        return self._request("POST", url, json_body=payload)
        return self._handle(r)

    # --------------------------
    # Pixels
    # --------------------------
    def upsert_pixel(self, graph_id: str, yyyymmdd: str, quantity: int) -> Dict[str, Any]:
        """
        PUT /v1/users/<username>/graphs/<graphID>/<yyyyMMdd>
        Creates or updates the pixel for that date.
        """
        url = f"{self.base_url}/{self.username}/graphs/{graph_id}/{yyyymmdd}"
        payload = {"quantity": str(int(quantity))}
        return self._request("PUT", url, json_body=payload)

    def get_pixel(self, graph_id: str, yyyymmdd: str) -> Optional[Dict[str, Any]]:
        """
        GET /v1/users/<username>/graphs/<graphID>/<yyyyMMdd>
        If no pixel exists, Pixela typically returns 404.
        """
        url = f"{self.base_url}/{self.username}/graphs/{graph_id}/{yyyymmdd}"
        r = requests.get(url, headers=self._headers(), timeout=30)
        if r.status_code == 404:
            return None
        # Use handler for non-404 responses
        return self._handle(r)

    def get_pixels_range(self, graph_id: str, date_from: str, date_to: str) -> Dict[str, Any]:
        """
        GET /v1/users/<username>/graphs/<graphID>/pixels?from=...&to=...&withBody=true
        Returns: {"pixels":[{"date":"YYYYMMDD","quantity":"1"}, ...]}
        """
        url = f"{self.base_url}/{self.username}/graphs/{graph_id}/{yyyymmdd}"
        return self._request("GET", url, params=params)
