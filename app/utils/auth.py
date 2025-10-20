"""
Better Auth Session Validation for Flask API

This module validates sessions created by Better Auth (Next.js).
Python API acts as a read-only validator - it does not create sessions or manage auth.
"""
from datetime import datetime
from functools import wraps
from flask import request, jsonify, current_app, g
from app import db
from app.models.user import User, Session


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


def validate_better_auth_session(session_token, track_login=False):
    """
    Validate Better Auth session token
    Simple database lookup - no JWT decoding or token hashing

    Args:
        session_token: The session token to validate
        track_login: If True, update last_login and create audit log entry
    """
    try:
        from urllib.parse import unquote

        # URL decode the session token (cookies may be URL encoded)
        decoded_token = unquote(session_token)

        # Better Auth tokens are formatted as: {session_id}.{signature}
        # We only need the session_id part (before the dot)
        token_parts = decoded_token.split('.')
        session_id = token_parts[0] if token_parts else decoded_token

        # Look up session by token field (Better Auth stores the session ID here)
        session = Session.query.filter_by(token=session_id).first()

        if not session:
            current_app.logger.error(f"Session not found for token: {session_id[:30]}...")
            raise AuthError('Invalid session')

        # Check if session is expired
        if not session.is_valid():
            raise AuthError('Session expired')

        # Load user
        user = User.query.get(session.user_id)

        if not user:
            raise AuthError('User not found')

        if not user.is_active:
            raise AuthError('User account is inactive')

        # Track login if requested
        if track_login:
            old_last_login = user.last_login
            user.last_login = datetime.utcnow()

            # Create audit log entry for login
            from app.utils.audit import create_audit_log
            create_audit_log(
                table_name='users',
                record_id=user.id,
                action='LOGIN',
                old_values={'last_login': old_last_login.isoformat() if old_last_login else None},
                new_values={'last_login': user.last_login.isoformat()},
                user_email=user.email,
                reason='User login event'
            )

            try:
                db.session.commit()
            except Exception as commit_error:
                current_app.logger.error(f"Failed to track login: {commit_error}")
                db.session.rollback()

        return {
            'user_id': user.id,
            'email': user.email,
            'role': user.role,
            'session_id': session.id,
            'user': user
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


# =============================================================================
# Session Management Functions (Better Auth Only - Python Does Not Create Sessions)
# =============================================================================
# The following functions are NOT USED in Better Auth mode.
# Better Auth (Next.js) handles all session creation, refresh, and revocation.
# Python API only validates existing sessions created by Better Auth.
#
# If you need to create sessions for Python-only endpoints, use Better Auth
# API routes instead.
# =============================================================================

def cleanup_expired_sessions():
    """
    Clean up expired Better Auth sessions (optional maintenance task)
    Can be run as a scheduled job for database cleanup
    """
    expired_sessions = Session.query.filter(
        Session.expires_at < datetime.utcnow()
    ).all()

    for session in expired_sessions:
        db.session.delete(session)

    db.session.commit()
    return len(expired_sessions)
