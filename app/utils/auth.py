"""
Better Auth Session Validation for Flask API

This module validates sessions created by Better Auth (Next.js).
Sessions are stored in Redis for stateless, horizontally scalable architecture.
Python API acts as a read-only validator - it does not create sessions or manage auth.
"""
from functools import wraps
from flask import request, jsonify, current_app, g
from app.utils.redis_session import get_session_validator
from urllib.parse import unquote
from types import SimpleNamespace


class AuthError(Exception):
    """Authentication error exception"""
    def __init__(self, message, status_code=401):
        self.message = message
        self.status_code = status_code


def get_session_token():
    """
    Extract session token from request
    Supports:
    - Authorization: Bearer <session_id>
    - Cookie: better-auth.session_token=<session_id>
    - X-Session-Token: <session_id>
    """
    # Try Authorization header first
    auth_header = request.headers.get('Authorization')
    if auth_header:
        try:
            scheme, token = auth_header.split(' ', 1)
            if scheme.lower() == 'bearer':
                return token
        except ValueError:
            pass

    # Try custom header
    session_header = request.headers.get('X-Session-Token')
    if session_header:
        return session_header

    # Try cookie (Better Auth default cookie name pattern)
    # Better Auth typically uses cookies named like 'better-auth.session_token'
    for cookie_name, cookie_value in request.cookies.items():
        if 'session' in cookie_name.lower():
            return cookie_value

    raise AuthError('No session token provided')


def validate_better_auth_session(session_token):
    """
    Validate Better Auth session token from Redis

    Args:
        session_token: The session token to validate
    """
    try:

        # URL decode the session token (cookies may be URL encoded)
        decoded_token = unquote(session_token)
        current_app.logger.info(f"[Flask Auth] Raw session token: {session_token[:30]}...")
        current_app.logger.info(f"[Flask Auth] Decoded token: {decoded_token[:30]}...")

        # Better Auth tokens are formatted as: {session_id}.{signature}
        # We only need the session_id part (before the dot)
        token_parts = decoded_token.split('.')
        session_id = token_parts[0] if token_parts else decoded_token
        current_app.logger.info(f"[Flask Auth] Extracted session_id: {session_id[:30]}...")
        current_app.logger.info(f"[Flask Auth] Token had {len(token_parts)} parts")

        # Look up session in Redis
        session_validator = get_session_validator()
        session_data = session_validator.get_session(session_id)

        if not session_data:
            current_app.logger.error(f"Session not found in Redis: {session_id[:30]}...")
            raise AuthError('Invalid session')

        user_payload = session_data.get('user') or {}

        # Extract user details directly from session payload
        user_id = user_payload.get('id') or session_data.get('userId')
        if not user_id:
            raise AuthError('Invalid session data')

        user_email = user_payload.get('email') or session_data.get('userEmail')
        user_role = user_payload.get('role') or session_data.get('userRole') or 'user'
        is_active = user_payload.get('isActive', True)

        if not is_active:
            raise AuthError('User account is inactive')

        # Build a lightweight user object for downstream consumers
        user_object = SimpleNamespace(
            id=str(user_id),
            email=user_email,
            role=user_role,
            is_active=is_active,
            name=user_payload.get('name'),
            metadata=user_payload.get('metadata'),
        )

        return {
            'user_id': str(user_id),
            'email': user_email,
            'role': user_role,
            'session_id': session_id,
            'user': user_object,
            'session': session_data,
        }

    except AuthError:
        raise
    except Exception as e:
        current_app.logger.error(f"Session validation error: {str(e)}")
        raise AuthError('Session validation failed')


def require_auth(f):
    """Decorator to require Better Auth session authentication for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Extract session token
            session_token = get_session_token()

            # Validate session
            user_info = validate_better_auth_session(session_token)

            # Store user information in Flask g object
            g.current_user_id = user_info['user_id']
            g.current_user_email = user_info['email']
            g.current_user_role = user_info['role']
            g.current_user = user_info['user']
            g.session_id = user_info['session_id']

            return f(*args, **kwargs)

        except AuthError as e:
            return jsonify({
                'error': 'Authentication failed',
                'message': e.message
            }), e.status_code
        except Exception as e:
            current_app.logger.error(f"Authentication error: {str(e)}")
            return jsonify({
                'error': 'Authentication failed',
                'message': 'Internal authentication error'
            }), 500

    return decorated_function


def admin_required(f):
    """Decorator to require admin role for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user_role') or g.current_user_role != 'admin':
            return jsonify({
                'error': 'Access denied',
                'message': 'Admin role required'
            }), 403

        return f(*args, **kwargs)

    return decorated_function


def user_or_admin_required(f):
    """Decorator to require user or admin role for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user_role') or g.current_user_role not in ['user', 'admin']:
            return jsonify({
                'error': 'Access denied',
                'message': 'Valid user role required'
            }), 403

        return f(*args, **kwargs)

    return decorated_function


def get_current_user():
    """Get current authenticated user from Flask g object"""
    if hasattr(g, 'current_user'):
        return g.current_user
    return None


def get_current_user_id():
    """Get current authenticated user ID from Flask g object"""
    return getattr(g, 'current_user_id', None)


def is_admin():
    """Check if current user has admin role"""
    return getattr(g, 'current_user_role', None) == 'admin'
