"""
Utility helpers for issuing and validating JWT access tokens.

These tokens let the frontend talk to the Flask API (and other services)
without needing to forward Better Auth session cookies.
"""
import os
from datetime import datetime, timedelta

import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "replace-this-with-a-secure-secret")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXP_MINUTES = int(os.environ.get("JWT_EXP_MINUTES", 15))


def create_jwt_token(user_id: str, role: str) -> tuple[str, str]:
    """Return a tuple of (token string, ISO8601 expiry timestamp)."""
    expires_at = datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expires_at,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # PyJWT >= 2.0 returns a str; older versions return bytes.
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return token, expires_at.isoformat() + "Z"


def verify_jwt_token(token: str) -> dict:
    """Verify a JWT and return its payload; raises jwt exceptions on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
