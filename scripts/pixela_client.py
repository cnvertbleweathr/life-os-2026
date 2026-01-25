#!/usr/bin/env python3
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://pixe.la/v1/users"

# Retry defaults (override via env if you want)
PIXELA_MAX_RETRIES = int(os.environ.get("PIXELA_MAX_RETRIES", "6"))
PIXELA_BACKOFF_BASE_SEC = float(os.environ.get("PIXELA_BACKOFF_BASE_SEC", "0.8"))
PIXELA_BACKOFF_CAP_SEC = float(os.environ.get("PIXELA_BACKOFF_CAP_SEC", "12"))


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

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Pixela may reject ~25% of some requests for non-supporters (503).
        Retry transient failures with exponential backoff + jitter on 503/429 and other 5xx.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(PIXELA_MAX_RETRIES + 1):
            try:
                r = requests.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                    timeout=timeout,
                )

                if r.status_code in (429, 500, 502, 503, 504):
                    body = (r.text or "")[:300].lower()
                    should_retry = ("please retry" in body) or (r.status_code in (429, 503, 500, 502, 504))

                    if should_retry and attempt < PIXELA_MAX_RETRIES:
                        sleep_s = min(
                            PIXELA_BACKOFF_CAP_SEC,
                            PIXELA_BACKOFF_BASE_SEC * (2 ** attempt),
                        )
                        # jitter to avoid hammering
                        sleep_s *= (0.7 + random.random() * 0.6)
                        time.sleep(sleep_s)
                        continue

                return self._handle(r)

            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                if attempt < PIXELA_MAX_RETRIES:
                    sleep_s = min(
                        PIXELA_BACKOFF_CAP_SEC,
                        PIXELA_BACKOFF_BASE_SEC * (2 ** attempt),
                    )
                    sleep_s *= (0.7 + random.random() * 0.6)
                    time.sleep(sleep_s)
                    continue
                raise

        if last_exc:
            raise last_exc
        raise PixelaError("Pixela request failed after retries.")

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
        If no pixel exists, Pixela returns 404.
        """
        url = f"{self.base_url}/{self.username}/graphs/{graph_id}/{yyyymmdd}"
        r = requests.get(url, headers=self._headers(), timeout=30)
        if r.status_code == 404:
            return None
        return self._handle(r)

    def get_pixels_range(self, graph_id: str, date_from: str, date_to: str, with_body: bool = True) -> Dict[str, Any]:
        """
        GET /v1/users/<username>/graphs/<graphID>/pixels?from=...&to=...&withBody=true
        Returns: {"pixels":[{"date":"YYYYMMDD","quantity":"1"}, ...]}
        """
        url = f"{self.base_url}/{self.username}/graphs/{graph_id}/pixels"
        params = {
            "from": date_from,
            "to": date_to,
            "withBody": "true" if with_body else "false",
        }
        return self._request("GET", url, params=params)
