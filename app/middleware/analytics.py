from datetime import datetime
from flask import request, g, current_app
from app import db
from app.models.usage_analytics import UsageAnalytics


def init_usage_analytics(app):
    """Register request hooks for capturing usage analytics."""

    @app.before_request
    def track_page_view_start():
        try:
            # Only track GET navigations for now
            if request.method != 'GET':
                return

            g._page_view_start = datetime.utcnow()
        except Exception as e:
            current_app.logger.debug(f"Analytics before_request error: {e}")

    @app.after_request
    def track_page_view_end(response):
        try:
            # Only track GET navigations for now
            if request.method != 'GET':
                return response

            start = getattr(g, '_page_view_start', None)
            duration_seconds = None
            if start:
                duration_seconds = int((datetime.utcnow() - start).total_seconds())

            record = UsageAnalytics(
                user_id=getattr(g, 'current_user_id', None),
                session_id=str(getattr(g, 'session_id', '')) if hasattr(g, 'session_id') else None,
                route=request.path,
                page_title=None,
                referrer=request.referrer,
                duration_seconds=duration_seconds,
                action='page_view',
                context_metadata=None,
                user_agent=request.headers.get('User-Agent', '')[:500],
                ip_address=request.headers.get('X-Forwarded-For', request.remote_addr)
            )

            db.session.add(record)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.debug(f"Analytics after_request error: {e}")
        return response
