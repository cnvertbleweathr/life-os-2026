#!/usr/bin/env python3
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
load_dotenv()

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
        We still rely on HTTP status codes, but also surface Pixela message on failure.
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
        r = requests.post(url, headers=self._headers(), json=payload, timeout=30)
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
        r = requests.put(url, headers=self._headers(), json=payload, timeout=30)
        return self._handle(r)

    def get_pixel(self, graph_id: str, yyyymmdd: str) -> Optional[Dict[str, Any]]:
        """
        GET /v1/users/<username>/graphs/<graphID>/<yyyyMMdd>
        If no pixel exists, Pixela typically returns 404.
        """
        url = f"{self.base_url}/{self.username}/graphs/{graph_id}/{yyyymmdd}"
        r = requests.get(url, headers=self._headers(), timeout=30)
        if r.status_code == 404:
            return None
        return self._handle(r)  # includes quantity when present

    def get_pixels_range(self, graph_id: str, date_from: str, date_to: str) -> Dict[str, Any]:
        """
        GET /v1/users/<username>/graphs/<graphID>/pixels?from=...&to=...&withBody=true
        Returns: {"pixels":[{"date":"YYYYMMDD","quantity":"1"}, ...]}
        """
        url = f"{self.base_url}/{self.username}/graphs/{graph_id}/pixels"
        params = {"from": date_from, "to": date_to, "withBody": "true"}
        r = requests.get(url, headers=self._headers(), params=params, timeout=30)
        return self._handle(r)
