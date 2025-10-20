"""
Dashboard Routes - Statistics and overview data
"""
from flask import Blueprint, jsonify, current_app, g
from app import db
from app.models import Invoice, ProcessingJob
from app.utils.auth import require_auth, user_or_admin_required, is_admin
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, and_

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/stats', methods=['GET'])
@require_auth
@user_or_admin_required
def get_dashboard_stats():
    """Get dashboard statistics for the current user"""
    try:
        user_id = g.current_user_id

        # Get total invoices count
        if is_admin():
            # Admin sees all invoices
            total_invoices = Invoice.query.count()
        else:
            # Regular user sees only their invoices
            total_invoices = Invoice.query.filter_by(uploaded_by_user_id=user_id).count()

        # Get invoices processed today (created today)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        if is_admin():
            processed_today = Invoice.query.filter(
                Invoice.created_at >= today_start
            ).count()
        else:
            processed_today = Invoice.query.filter(
                and_(
                    Invoice.uploaded_by_user_id == user_id,
                    Invoice.created_at >= today_start
                )
            ).count()

        # Get pending review count (completed jobs that require review and haven't been auto-saved)
        if is_admin():
            pending_review = ProcessingJob.query.filter(
                and_(
                    ProcessingJob.status == 'completed',
                    ProcessingJob.result_data['requires_review'].astext.cast(db.Boolean) == True,
                    ProcessingJob.result_data['auto_saved'].astext.cast(db.Boolean) != True
                )
            ).count()
        else:
            pending_review = ProcessingJob.query.filter(
                and_(
                    ProcessingJob.user_id == user_id,
                    ProcessingJob.status == 'completed',
                    ProcessingJob.result_data['requires_review'].astext.cast(db.Boolean) == True,
                    ProcessingJob.result_data['auto_saved'].astext.cast(db.Boolean) != True
                )
            ).count()

        return jsonify({
            'total_invoices': total_invoices,
            'processed_today': processed_today,
            'pending_review': pending_review
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching dashboard stats: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard statistics'}), 500
