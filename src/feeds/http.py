"""Shared HTTP session for talking to Taiwan government servers.

Why this exists: Python 3.13+ turned on a stricter certificate check
(VERIFY_X509_STRICT). Many Taiwan government sites use certificates that are
valid and trusted but miss one optional field ("Subject Key Identifier"),
so Python rejects them with "CERTIFICATE_VERIFY_FAILED: Missing Subject Key
Identifier" even though browsers and curl accept them.

This session switches off only that extra strictness. Certificates are still
fully verified against trusted CAs and hostnames are still checked, so this
does NOT disable HTTPS security.
"""

from __future__ import annotations

import os
import ssl

import certifi
import requests
from requests.adapters import HTTPAdapter

USER_AGENT = "ACE-traffic-research/0.1 (personal open-data project)"


def _ssl_context() -> ssl.SSLContext:
    ca_file = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE") or certifi.where()
    ctx = ssl.create_default_context(cafile=ca_file)
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


class _GovTWAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = _ssl_context()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = _ssl_context()
        return super().proxy_manager_for(*args, **kwargs)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", _GovTWAdapter())
    return session


session = make_session()
