"""
calendar_export auth: refresh silently, never open a browser unattended.

The 2026-10-26 9am sync stalled because calendar_export went straight to a
browser login whenever the access token had expired (every run), instead of
using the saved refresh token.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from google.auth.exceptions import RefreshError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cal(monkeypatch):
    spec = importlib.util.spec_from_file_location("calendar_export", ROOT / "scripts/calendar_export.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "calendar_export", mod)
    spec.loader.exec_module(mod)

    def no_browser(*a, **k):
        raise AssertionError("opened a browser login during an unattended run")
    monkeypatch.setattr(mod.InstalledAppFlow, "from_client_secrets_file", no_browser)
    return mod


class FakeCreds:
    def __init__(self, valid=False, refresh_token="r1", refresh_fails=False):
        self.valid, self.refresh_token, self.refresh_fails = valid, refresh_token, refresh_fails
        self.expired = not valid
        self.refreshed = False

    def refresh(self, request):
        if self.refresh_fails:
            raise RefreshError("invalid_grant: Token has been expired or revoked.")
        self.valid, self.expired, self.refreshed = True, False, True

    def to_json(self):
        return json.dumps({"token": "new", "refresh_token": self.refresh_token})


def use(monkeypatch, cal, creds, tmp_path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(cal.Credentials, "from_authorized_user_file", lambda *a, **k: creds)
    return str(token)


def test_valid_token_used_as_is(cal, monkeypatch, tmp_path):
    creds = FakeCreds(valid=True)
    assert cal.get_credentials("creds.json", use(monkeypatch, cal, creds, tmp_path)) is creds
    assert not creds.refreshed


def test_expired_token_refreshes_silently_and_is_saved(cal, monkeypatch, tmp_path):
    creds = FakeCreds(valid=False)
    token = use(monkeypatch, cal, creds, tmp_path)
    assert cal.get_credentials("creds.json", token) is creds
    assert creds.refreshed
    assert json.loads(Path(token).read_text())["token"] == "new"


def test_revoked_refresh_token_fails_fast(cal, monkeypatch, tmp_path):
    token = use(monkeypatch, cal, FakeCreds(refresh_fails=True), tmp_path)
    with pytest.raises(cal.AuthRequired, match="--auth"):
        cal.get_credentials("creds.json", token)


def test_missing_token_fails_fast(cal, tmp_path):
    with pytest.raises(cal.AuthRequired, match="no saved token"):
        cal.get_credentials("creds.json", str(tmp_path / "nope.json"))


def test_main_exits_2_and_notifies(cal, monkeypatch, tmp_path, capsys):
    sent = []
    monkeypatch.setattr(cal, "_notify_reauth", sent.append)
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN", str(tmp_path / "nope.json"))
    monkeypatch.setattr("sys.argv", ["calendar_export.py", "--year", "2026"])
    assert cal.main() == 2
    assert "--auth" in capsys.readouterr().err and sent
