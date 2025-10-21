"""
Job Routes - User job tracking and management
"""
from flask import Blueprint, request, jsonify, current_app, g
from app import db
from app.models.processing_job import ProcessingJob
from app.models.file_storage import FileStorage
from app.utils.auth import require_auth, user_or_admin_required
from app.utils.routes_helpers import get_pagination_params, build_pagination_response, handle_db_error
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_

jobs_bp = Blueprint('jobs', __name__)


@jobs_bp.route('/my-jobs', methods=['GET'])
@require_auth
@user_or_admin_required
def get_my_jobs():
    """Get all jobs for the current user with pagination and filtering"""
    try:
        user_id = g.current_user_id
        page, per_page = get_pagination_params()
        status_filter = request.args.get('status')

        # Build query filtered by user_id
        query = ProcessingJob.query.filter_by(user_id=user_id)

        if status_filter:
            if status_filter == 'review_needed':
                # Filter for completed jobs that require review
                query = query.filter(
                    and_(
                        ProcessingJob.status == 'completed',
                        ProcessingJob.result_data['requires_review'].astext.cast(db.Boolean).is_(True)
                    )
                )
            else:
                query = query.filter(ProcessingJob.status == status_filter)

        # Get paginated results
        jobs = query.order_by(ProcessingJob.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Get job statistics for this user
        stats = db.session.query(
            ProcessingJob.status,
            func.count(ProcessingJob.id).label('count')
        ).filter(
            ProcessingJob.user_id == user_id
        ).group_by(ProcessingJob.status).all()

        # Get recent activity (last 24 hours)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        recent_jobs = ProcessingJob.query.filter(
            and_(
                ProcessingJob.user_id == user_id,
                ProcessingJob.created_at >= yesterday
            )
        ).count()

        # Get unread completed jobs (jobs that haven't been viewed)
        unread_completed = ProcessingJob.query.filter(
            and_(
                ProcessingJob.user_id == user_id,
                ProcessingJob.status.in_(['completed', 'failed']),
                ProcessingJob.viewed_at.is_(None)
            )
        ).count()

        return jsonify({
            'jobs': [job.to_dict() for job in jobs.items],
            'pagination': build_pagination_response(jobs),
            'statistics': {
                'total_jobs': jobs.total,
                'recent_jobs_24h': recent_jobs,
                'unread_completed': unread_completed,
                'status_breakdown': {
                    status: count for status, count in stats
                }
            }
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching user jobs: {str(e)}")
        return jsonify({'error': 'Failed to fetch jobs'}), 500


@jobs_bp.route('/my-jobs/<job_id>', methods=['GET'])
@require_auth
@user_or_admin_required
def get_my_job_details(job_id):
    """Get detailed information about a specific job for the current user"""
    try:
        user_id = g.current_user_id
        job = ProcessingJob.query.filter_by(
            id=job_id,
            user_id=user_id
        ).first_or_404()

        # Get related file storage info
        file_info = None
        if job.file_storage_id:
            file_storage = FileStorage.query.get(job.file_storage_id)
            if file_storage:
                file_info = {
                    'file_name': file_storage.file_name,
                    'file_size': file_storage.file_size,
                    'mime_type': file_storage.mime_type,
                    'upload_source': file_storage.upload_source,
                    'processing_status': file_storage.processing_status,
                    'blob_url': file_storage.blob_url
                }

        # Get processing logs if available
        logs = []
        if job.result_data and 'logs' in job.result_data:
            logs = job.result_data['logs']

        return jsonify({
            'job': job.to_dict(),
            'file_info': file_info,
            'logs': logs
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching job details: {str(e)}")
        return jsonify({'error': 'Failed to fetch job details'}), 500


@jobs_bp.route('/my-jobs/unread-count', methods=['GET'])
@require_auth
@user_or_admin_required
def get_unread_count():
    """Get count of unread/new completed jobs for the current user"""
    try:
        user_id = g.current_user_id

        # Get jobs that are completed/failed but haven't been viewed
        unread_count = ProcessingJob.query.filter(
            and_(
                ProcessingJob.user_id == user_id,
                ProcessingJob.status.in_(['completed', 'failed']),
                ProcessingJob.viewed_at.is_(None)
            )
        ).count()

        return jsonify({
            'unread_count': unread_count
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching unread count: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({'error': 'Failed to fetch unread count'}), 500


@jobs_bp.route('/my-jobs/mark-as-read', methods=['POST'])
@require_auth
@user_or_admin_required
def mark_jobs_as_read():
    """Mark one or all completed jobs as read/viewed"""
    try:
        user_id = g.current_user_id
        current_app.logger.info(f"Mark as read - user_id: {user_id}, type: {type(user_id)}")

        data = request.get_json() or {}
        job_id = data.get('job_id')
        current_app.logger.info(f"Mark as read - job_id from request: {job_id}")

        if job_id:
            # Convert job_id string to UUID
            try:
                import uuid
                job_uuid = uuid.UUID(job_id)
            except (ValueError, AttributeError):
                return jsonify({'error': 'Invalid job ID format'}), 400

            # Mark specific job as read
            job = ProcessingJob.query.filter_by(
                id=job_uuid,
                user_id=user_id
            ).first()

            if not job:
                return jsonify({'error': 'Job not found'}), 404

            if job.viewed_at is None:
                job.viewed_at = datetime.now(timezone.utc)
                db.session.commit()

            return jsonify({
                'message': 'Job marked as read',
                'job_id': str(job_id)
            })
        else:
            # Mark all completed/failed jobs as read
            current_app.logger.info(f"Marking all jobs as read for user {user_id}")

            jobs_to_mark = ProcessingJob.query.filter(
                and_(
                    ProcessingJob.user_id == user_id,
                    ProcessingJob.status.in_(['completed', 'failed']),
                    ProcessingJob.viewed_at.is_(None)
                )
            ).all()

            current_app.logger.info(f"Found {len(jobs_to_mark)} jobs to mark as read")

            current_time = datetime.now(timezone.utc)
            for job in jobs_to_mark:
                job.viewed_at = current_time

            db.session.commit()
            current_app.logger.info(f"Successfully marked {len(jobs_to_mark)} jobs as read")

            return jsonify({
                'message': 'All jobs marked as read',
                'count': len(jobs_to_mark)
            })

    except Exception as e:
        current_app.logger.error(f"Error marking jobs as read: {str(e)}")
        current_app.logger.error(f"Error type: {type(e).__name__}")
        current_app.logger.error(f"Error args: {e.args}")
        current_app.logger.exception(e)
        return handle_db_error(e, 'Failed to mark jobs as read')
