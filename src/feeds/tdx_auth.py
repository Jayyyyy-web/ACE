"""Authentication for the TDX (Transport Data eXchange) API.

TDX uses the OIDC client-credentials flow: we trade our Client Id and
Client Secret for a short-lived access token, then send that token as a
Bearer header on every API call.

The token endpoint is rate-limited per IP, so we cache the token in memory
and only request a new one shortly before it expires.
"""

from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv

TOKEN_URL = (
    "https://tdx.transportdata.tw/auth/realms/TDXConnect/"
    "protocol/openid-connect/token"
)

# Refresh this many seconds before the real expiry, to avoid using a token
# that dies mid-request.
EXPIRY_MARGIN_SECONDS = 60


class TDXAuthError(RuntimeError):
    """Raised when we can't get a token from TDX."""


class TDXAuth:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        load_dotenv()
        self.client_id = client_id or os.getenv("TDX_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("TDX_CLIENT_SECRET")
        self._token: str | None = None
        self._expires_at: float = 0.0

        if not self.client_id or not self.client_secret:
            raise TDXAuthError(
                "TDX_CLIENT_ID and TDX_CLIENT_SECRET are missing. "
                "Copy .env.example to .env and fill in your keys from the TDX member centre."
            )
        if "your_client" in self.client_id or "your_client" in self.client_secret:
            raise TDXAuthError(".env still has the placeholder values. Put your real TDX keys in it.")

    def get_token(self) -> str:
        """Return a valid access token, fetching a new one only when needed."""
        if self._token and time.time() < self._expires_at:
            return self._token

        try:
            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
        except requests.RequestException as e:
            raise TDXAuthError(f"Could not reach the TDX token endpoint: {e}") from e

        if resp.status_code != 200:
            raise TDXAuthError(
                f"TDX refused the token request (HTTP {resp.status_code}). "
                "Check your Client Id / Secret and that your TDX account has been approved."
            )

        payload = resp.json()
        self._token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._expires_at = time.time() + max(expires_in - EXPIRY_MARGIN_SECONDS, 0)
        return self._token

    def headers(self) -> dict:
        """Headers to send with every TDX API request."""
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Accept-Encoding": "gzip",
        }


# One shared instance so the whole app reuses the same cached token.
_default_auth: TDXAuth | None = None


def get_auth() -> TDXAuth:
    global _default_auth
    if _default_auth is None:
        _default_auth = TDXAuth()
    return _default_auth


def get_token() -> str:
    return get_auth().get_token()


if __name__ == "__main__":
    token = get_token()
    print(f"Got a TDX token: {token[:12]}... (length {len(token)})")
