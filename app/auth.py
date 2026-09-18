"""Single-password session auth. Hermes is a personal, single-user app —
there's no account system, just one shared password gating access, backed
by a signed cookie so the browser doesn't have to keep resending it.

Deliberately app-level rather than enforced at the Traefik Ingress: Hermes
is also reachable via a NodePort (see k8s/hermes-api.yaml) so phones/tablets
on the LAN can hit it by bare IP:port with no DNS/hosts setup, and a
NodePort routes straight to the pod, bypassing Traefik and any
ingress-level middleware entirely. Checking auth inside the app itself
covers both paths with one implementation instead of two.
"""

import hmac
import time
from hashlib import sha256

from app.config import AUTH_PASSWORD, SESSION_SECRET

COOKIE_NAME = "hermes_session"
SESSION_LIFETIME_SECONDS = 90 * 24 * 60 * 60  # 90 days — a phone shouldn't need re-login every visit


def _sign(expiry: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), expiry.encode(), sha256).hexdigest()


def check_password(password: str) -> bool:
    return hmac.compare_digest(password, AUTH_PASSWORD)


def create_session_token() -> str:
    expiry = str(int(time.time()) + SESSION_LIFETIME_SECONDS)
    return f"{expiry}.{_sign(expiry)}"


def verify_session_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expiry, signature = token.split(".", 1)
    if not hmac.compare_digest(signature, _sign(expiry)):
        return False
    return int(expiry) > time.time()
