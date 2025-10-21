"""
Redis Session Validation for Flask API

Validates sessions stored in Redis by Better Auth (Next.js frontend).
Flask API validates sessions but does not create them.
"""
import json
import redis
from datetime import datetime
from flask import current_app


class RedisSessionValidator:
    """
    Redis-based session validator for Better Auth sessions
    Uses Redis database 2 (same as frontend) for session storage
    """

    def __init__(self):
        """Initialize Redis connection for session validation"""
        redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379')
        session_db = current_app.config.get('REDIS_SESSION_DB', 2)

        # Connect to Redis session database (db 2)
        try:
            self.redis = redis.from_url(
                f"{redis_url}/{session_db}",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis.ping()
            current_app.logger.info(f"Redis session validator connected to {redis_url}/{session_db}")
        except Exception as e:
            current_app.logger.error(f"Failed to connect to Redis for sessions: {e}")
            raise

    def get_session(self, token: str) -> dict | None:
        """
        Get session from Redis

        Args:
            token: Session token

        Returns:
            Session data dict or None if not found/expired
        """
        key = f"session:{token}"
        current_app.logger.info(f"[Flask Redis] GET session with token: {token[:20]}...")
        current_app.logger.info(f"[Flask Redis] Constructed key: {key[:50]}...")

        try:
            data = self.redis.get(key)
            if not data:
                current_app.logger.warning(f"[Flask Redis] Session not found for key: {key[:50]}...")
                # Try to see what keys actually exist
                all_keys = self.redis.keys("*")[:10]  # Sample first 10 keys
                current_app.logger.info(f"[Flask Redis] Sample keys in Redis: {all_keys}")
                return None

            session = json.loads(data)

            # Check if expired
            expires_at_str = session.get('expiresAt')
            if expires_at_str:
                # Handle both ISO format with and without 'Z'
                expires_at_str = expires_at_str.replace('Z', '+00:00')
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                except ValueError:
                    # Fallback: try parsing as timestamp
                    expires_at = datetime.fromtimestamp(float(expires_at_str) / 1000)

                if expires_at < datetime.utcnow().replace(tzinfo=expires_at.tzinfo):
                    self.delete_session(token)
                    return None

            return session
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Failed to decode session data: {e}")
            return None
        except Exception as e:
            current_app.logger.error(f"Redis session lookup failed: {e}")
            return None

    def delete_session(self, token: str):
        """
        Delete session from Redis

        Args:
            token: Session token to delete
        """
        key = f"session:{token}"
        try:
            self.redis.delete(key)
            current_app.logger.info(f"Deleted session: {token[:20]}...")
        except Exception as e:
            current_app.logger.error(f"Failed to delete session: {e}")

    def get_user_sessions(self, user_id: str) -> list[dict]:
        """
        Get all active sessions for a user

        Args:
            user_id: User ID

        Returns:
            List of session dicts
        """
        try:
            user_sessions_key = f"user-sessions:{user_id}"
            tokens = self.redis.smembers(user_sessions_key)

            sessions = []
            for token in tokens:
                session = self.get_session(token)
                if session:
                    sessions.append(session)

            return sessions
        except Exception as e:
            current_app.logger.error(f"Failed to get user sessions: {e}")
            return []

    def delete_user_sessions(self, user_id: str):
        """
        Delete all sessions for a user

        Args:
            user_id: User ID
        """
        try:
            user_sessions_key = f"user-sessions:{user_id}"
            tokens = self.redis.smembers(user_sessions_key)

            for token in tokens:
                self.delete_session(token)

            self.redis.delete(user_sessions_key)
            current_app.logger.info(f"Deleted all sessions for user: {user_id}")
        except Exception as e:
            current_app.logger.error(f"Failed to delete user sessions: {e}")

    def health_check(self) -> bool:
        """
        Check if Redis connection is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            return self.redis.ping()
        except Exception:
            return False


# Global session validator instance (initialized on first use)
_session_validator = None


def get_session_validator() -> RedisSessionValidator:
    """
    Get or create Redis session validator instance

    Returns:
        RedisSessionValidator instance
    """
    global _session_validator
    if _session_validator is None:
        _session_validator = RedisSessionValidator()
    return _session_validator
