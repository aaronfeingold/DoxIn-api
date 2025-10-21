"""
Shared utility functions for route handlers
"""
import redis
import os
from flask import request, jsonify, current_app
from app import db


def get_redis_connection():
    """Get Redis connection for monitoring and caching"""
    try:
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        return redis.from_url(redis_url)
    except Exception as e:
        current_app.logger.error(f"Redis connection error: {str(e)}")
        return None


def get_pagination_params():
    """Extract and validate pagination parameters from request"""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    return page, per_page


def build_pagination_response(paginated_query):
    """Build standard pagination response object"""
    return {
        'page': paginated_query.page,
        'per_page': paginated_query.per_page,
        'total': paginated_query.total,
        'pages': paginated_query.pages,
        'has_next': paginated_query.has_next,
        'has_prev': paginated_query.has_prev
    }


def handle_db_error(error, message, status_code=500):
    """Handle database errors with consistent logging and rollback"""
    db.session.rollback()
    current_app.logger.error(f"{message}: {str(error)}")
    return jsonify({'error': message}), status_code


def handle_error(error, message, status_code=500, include_details=False):
    """
    Handle general errors with consistent logging

    Args:
        error: The exception that was raised
        message: User-friendly error message
        status_code: HTTP status code to return
        include_details: Whether to include error details in response (use cautiously)
    """
    current_app.logger.error(f"{message}: {str(error)}")

    response = {'error': message}
    if include_details:
        response['details'] = str(error)

    return jsonify(response), status_code
