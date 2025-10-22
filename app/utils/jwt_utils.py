"""
Utility helpers for issuing and validating JWT access tokens.

These tokens let the frontend talk to the Flask API (and other services)
without needing to forward Better Auth session cookies.
"""
from datetime import datetime, timedelta

import jwt
from flask import current_app


def create_jwt_token(user_id: str, role: str) -> tuple[str, str]:
    """Return a tuple of (token string, ISO8601 expiry timestamp)."""
    expires_at = datetime.utcnow() + timedelta(minutes=current_app.config['JWT_EXP_MINUTES'])
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expires_at,
    }
    token = jwt.encode(payload, current_app.config['JWT_SECRET'], algorithm=current_app.config['JWT_ALGORITHM'])

    # PyJWT >= 2.0 returns a str; older versions return bytes.
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return token, expires_at.isoformat() + "Z"


def verify_jwt_token(token: str) -> dict:
    """Verify a JWT and return its payload; raises jwt exceptions on failure."""
    return jwt.decode(token, current_app.config['JWT_SECRET'], algorithms=[current_app.config['JWT_ALGORITHM']])
