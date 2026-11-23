"""
How often daily_sync posts the check-in packet.

Set ONS_CHECKIN_CADENCE in .env:
    daily          every day (default)
    weekdays       Monday to Friday
    weekly:<day>   once a week, e.g. weekly:sun, weekly:monday

Returns the weekday numbers daily_sync's Step.run_on_days expects
(Monday = 0), or None for every day.
"""

from __future__ import annotations

import os

ENV_VAR = "ONS_CHECKIN_CADENCE"
DEFAULT = "daily"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse(value: str | None) -> list[int] | None:
    """Cadence string → run_on_days. Raises ValueError on anything unrecognised."""
    v = (value or DEFAULT).strip().lower()
    if v == "daily":
        return None
    if v == "weekdays":
        return [0, 1, 2, 3, 4]
    if v.startswith("weekly:"):
        day = v.split(":", 1)[1].strip()[:3]
        if day in DAYS:
            return [DAYS.index(day)]
    raise ValueError(f"{ENV_VAR}={value!r}: use daily, weekdays, or weekly:<day> (e.g. weekly:sun)")


def run_on_days(value: str | None = None) -> tuple[list[int] | None, str | None]:
    """(run_on_days, warning). A bad value falls back to daily so the sync never breaks."""
    if value is None:
        value = os.getenv(ENV_VAR)
    try:
        return parse(value), None
    except ValueError as e:
        return None, f"{e}; posting daily instead"
