#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.pixela_client import PixelaClient


GRAPHS = [
    ("meditation", "Meditation"),
    ("pushups100", "100 Pushups"),
    ("nonfiction10", "10 Pages Non-Fiction"),
    ("fiction10", "10 Pages Fiction"),
]


def main() -> None:
    px = PixelaClient.from_env()
    for gid, name in GRAPHS:
        try:
            res = px.create_graph(gid, name, unit="did", graph_type="int", color="shibafu", timezone="America/Denver")
            print(gid, res)
        except Exception as e:
            # If graph already exists, Pixela may return an error message.
            # We print and continue so it's safe to re-run.
            print(gid, f"ERROR: {e}")


if __name__ == "__main__":
    main()
