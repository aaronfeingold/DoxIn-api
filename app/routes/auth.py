"""
Authentication Routes - Login tracking and auth-related endpoints
"""
from flask import Blueprint, jsonify, request, current_app, g
from app import db
from app.models.user import User
from app.models.usage_analytics import UsageAnalytics
from app.utils.auth import require_auth
from app.utils.audit import create_audit_log
from app.utils.jwt_utils import create_jwt_token
from datetime import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/track-login', methods=['POST'])
@require_auth
def track_login():
    """
    Track user login event - updates last_login timestamp,
    creates audit log entry, and tracks in usage analytics
    """
    try:
        user_id = g.current_user_id
        user_email = g.current_user_email

        # Get user
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Store old last_login for audit trail
        old_last_login = user.last_login

        # Update last_login timestamp
        user.last_login = datetime.utcnow()

        # Create audit log entry
        create_audit_log(
            table_name='users',
            record_id=user.id,
            action='LOGIN',
            old_values={'last_login': old_last_login.isoformat() if old_last_login else None},
            new_values={'last_login': user.last_login.isoformat()},
            user_email=user_email,
            reason='User login event'
        )

        # Track in usage analytics
        analytics_record = UsageAnalytics(
            user_id=user_id,
            session_id=str(g.session_id) if hasattr(g, 'session_id') else None,
            route='/auth/login',
            page_title='User Login',
            referrer=request.referrer,
            action='login',
            context_metadata={
                'login_method': 'email_password',
                'user_agent': request.headers.get('User-Agent', '')[:500]
            },
            user_agent=request.headers.get('User-Agent', '')[:500],
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr)
        )
        db.session.add(analytics_record)

        # Commit all changes
        db.session.commit()

        current_app.logger.info(f"Login tracked for user {user_email}")

        return jsonify({
            'success': True,
            'last_login': user.last_login.isoformat()
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error tracking login: {str(e)}")
        return jsonify({'error': 'Failed to track login'}), 500


@auth_bp.route('/jwt-token', methods=['POST'])
@require_auth
def get_jwt_token():
    """
    Issue a short-lived JWT for the authenticated Better Auth session.
    """
    try:
        user_id = g.current_user_id
        user_role = g.current_user_role
        token, expires_at = create_jwt_token(user_id, user_role)
        current_app.logger.info(f"Issued JWT for user {user_id}, expires at {expires_at}")
        return jsonify({"token": token, "expires_at": expires_at}), 200
    except Exception as e:
        current_app.logger.error(f"Failed to issue JWT: {str(e)}")
        return jsonify({'error': 'Failed to issue JWT'}), 500
