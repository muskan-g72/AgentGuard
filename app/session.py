"""Signed anonymous browser-session cookies.

The cookie contains only a random opaque identifier and an HMAC.  It is not an
identity token and carries no user data; ownership is enforced by SQLite rows.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets


class SessionSigner:
    def __init__(self, secret: str):
        if not secret:
            raise ValueError("A session signing secret is required.")
        self._key = secret.encode("utf-8")

    def sign(self, session_id: str) -> str:
        mac = hmac.new(self._key, session_id.encode(), hashlib.sha256).hexdigest()
        return f"{session_id}.{mac}"

    def issue(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(24)
        return session_id, self.sign(session_id)

    def verify(self, value: str | None) -> str | None:
        if not value or "." not in value:
            return None
        session_id, mac = value.rsplit(".", 1)
        if len(session_id) < 20 or not hmac.compare_digest(mac, self.sign(session_id).rsplit(".", 1)[1]):
            return None
        return session_id
