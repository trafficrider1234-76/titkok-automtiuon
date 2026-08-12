"""
TikTok OAuth — token acquisition, persistence, and automatic refresh.

Flow
----
1. First-time setup:  run  python setup_auth.py
   - Opens a browser for the user to authorise the app.
   - A tiny local server receives the ?code= redirect.
   - The code is exchanged for an access_token + refresh_token, which are
     persisted to data/token.json.

2. Daily runs:  TikTokAuth.load() reads token.json.  If the access_token is
   expired (or about to expire) the refresh_token is used automatically to
   obtain a fresh pair — no manual intervention needed.

Tokens are stored as JSON in data/token.json (git-ignored).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

import requests

from .config import CONFIG
from .logger import logger

# Token expiry safety margin (seconds) — refresh 5 min before expiry
_REFRESH_MARGIN = 300


class TikTokAuth:
    """Manages TikTok user access tokens with automatic refresh."""

    def __init__(self) -> None:
        self.token_file: Path = CONFIG.token_file
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._expires_at: float = 0.0
        self._open_id: str = ""

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing first if necessary."""
        self.load()
        if self._needs_refresh():
            self._do_refresh()
        return self._access_token

    @property
    def open_id(self) -> str:
        if not self._open_id:
            self.load()
        return self._open_id

    def load(self) -> None:
        """Load persisted tokens from disk (if present)."""
        if not self.token_file.exists():
            raise RuntimeError(
                "No TikTok token found. Run  python setup_auth.py  first to "
                "authorise your account."
            )
        data = json.loads(self.token_file.read_text())
        self._access_token = data.get("access_token", "")
        self._refresh_token = data.get("refresh_token", "")
        self._expires_at = float(data.get("expires_at", 0))
        self._open_id = data.get("open_id", "")
        logger.debug(
            "Loaded token — expires in %.0f min", max(self._expires_at - time.time(), 0) / 60
        )

    def save(self, token_data: dict) -> None:
        """Persist a fresh token response to disk."""
        now = time.time()
        self._access_token = token_data["access_token"]
        self._refresh_token = token_data["refresh_token"]
        self._expires_at = now + float(token_data.get("expires_in", 86400))
        self._open_id = token_data.get("open_id", self._open_id)

        payload = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expires_at": self._expires_at,
            "open_id": self._open_id,
            "saved_at": now,
        }
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(payload, indent=2))
        logger.info("Token saved to %s", self.token_file)

    # ------------------------------------------------------------------
    # First-time authorisation (interactive, run via setup_auth.py)
    # ------------------------------------------------------------------

    def authorise_interactive(self) -> None:
        """Run the full OAuth authorisation-code flow in a browser."""
        state = f"st{int(time.time())}"
        params = {
            "client_key": CONFIG.tiktok_client_key,
            "scope": CONFIG.tiktok_scope,
            "response_type": "code",
            "redirect_uri": CONFIG.tiktok_redirect_uri,
            "state": state,
        }
        auth_url = f"{CONFIG.tiktok_auth_base}?{urllib.parse.urlencode(params)}"

        logger.info("Opening browser for TikTok authorisation…")
        print("\n  ➜  If a browser doesn't open, visit this URL:\n")
        print(f"     {auth_url}\n")
        webbrowser.open(auth_url)

        # Capture the redirect on a local server
        code = _RedirectServer.capture_code(
            port=8765, expected_state=state, timeout=300
        )
        if not code:
            raise RuntimeError("Did not receive an authorisation code from TikTok.")

        token_data = self._exchange_code(code)
        self.save(token_data)
        logger.info("TikTok authorisation complete — token persisted.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _needs_refresh(self) -> bool:
        return (self._expires_at - time.time()) < _REFRESH_MARGIN

    def _do_refresh(self) -> None:
        logger.info("Access token expiring soon — refreshing…")
        resp = requests.post(
            CONFIG.tiktok_token_url,
            params={
                "client_key": CONFIG.tiktok_client_key,
                "client_secret": CONFIG.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        data = resp.json()
        if data.get("error") and data["error"] != "ok":
            raise RuntimeError(f"TikTok token refresh failed: {data}")
        # TikTok returns the token inside data.access_token
        token_data = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_in": data.get("expires_in", 86400),
            "open_id": data.get("open_id", self._open_id),
        }
        self.save(token_data)
        logger.info("Token refreshed successfully.")

    def _exchange_code(self, code: str) -> dict:
        """Exchange an authorisation code for access + refresh tokens."""
        resp = requests.post(
            CONFIG.tiktok_token_url,
            params={
                "client_key": CONFIG.tiktok_client_key,
                "client_secret": CONFIG.tiktok_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        data = resp.json()
        if not data.get("access_token"):
            raise RuntimeError(f"TikTok code exchange failed: {data}")
        return data


# ------------------------------------------------------------------
# Local redirect server — captures ?code= from TikTok's OAuth redirect
# ------------------------------------------------------------------


class _RedirectHandler(BaseHTTPRequestHandler):
    """Handles the /callback redirect from TikTok."""

    # Set by the server before each run
    expected_state: str = ""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path != "/callback":
            self._respond(404, "Not found — expecting /callback")
            return

        if params.get("state", [""])[0] != _RedirectHandler.expected_state:
            self._respond(422, "State mismatch — possible CSRF. Aborting.")
            return

        code = params.get("code", [""])[0]
        if code:
            self.server.received_code = code  # type: ignore[attr-defined]
            self._respond(200, "Authorisation received! You can close this tab.")
        else:
            err = params.get("error", ["unknown"])[0]
            self.server.received_code = ""  # type: ignore[attr-defined]
            self._respond(400, f"Authorisation failed: {err}")

    def _respond(self, status: int, msg: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = f"<html><body style='font-family:sans-serif;padding:40px'><h2>{msg}</h2></body></html>"
        self.wfile.write(body.encode())

    def log_message(self, fmt: str, *args) -> None:  # silence default logging
        pass


class _RedirectServer(HTTPServer):
    """HTTPServer that captures the OAuth redirect code."""

    received_code: str = ""

    @classmethod
    def capture_code(cls, port: int, expected_state: str, timeout: int = 300) -> Optional[str]:
        _RedirectHandler.expected_state = expected_state
        server = cls(("127.0.0.1", port), _RedirectHandler)
        server.timeout = 1
        logger.info("Listening for OAuth redirect on http://127.0.0.1:%d/callback …", port)

        elapsed = 0
        while elapsed < timeout:
            server.handle_request()
            if server.received_code:
                server.server_close()
                return server.received_code
            elapsed += 1

        server.server_close()
        return None
