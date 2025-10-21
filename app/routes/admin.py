"""
Admin monitoring routes for system health and job status
"""
from flask import Blueprint, jsonify, current_app, request
from app.utils.auth import require_auth, admin_required
from app import db
from app.models import ProcessingJob
from app.models.file_storage import FileStorage
from sqlalchemy import text, func
from datetime import datetime, timedelta
import redis
import os
import psutil

admin_bp = Blueprint('admin', __name__)


def get_redis_connection():
    """Get Redis connection for monitoring"""
    try:
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        return redis.from_url(redis_url)
    except Exception as e:
        current_app.logger.error(f"Redis connection error: {str(e)}")
        return None


@admin_bp.route('/health', methods=['GET'])
@require_auth
@admin_required
def admin_health_check():
    """Comprehensive admin health check for all services"""
    health_status = {
        'timestamp': datetime.utcnow().isoformat(),
        'overall_status': 'healthy',
        'services': {}
    }

    overall_healthy = True

    # Check Flask API
    health_status['services']['flask_api'] = {
        'status': 'healthy',
        'uptime': 'running',
        'version': '1.0.0'
    }

    # Check Database
    try:
        db.session.execute(text('SELECT 1'))
        db_stats = db.session.execute(text("""
            SELECT
                COUNT(*) as total_connections,
                (SELECT setting FROM pg_settings WHERE name = 'max_connections') as max_connections
            FROM pg_stat_activity
        """)).fetchone()

        health_status['services']['postgres'] = {
            'status': 'healthy',
            'connections': {
                'current': db_stats.total_connections,
                'max': db_stats.max_connections
            },
            'message': 'Database connected'
        }
    except Exception as e:
        health_status['services']['postgres'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
        overall_healthy = False

    # Check Redis
    redis_conn = get_redis_connection()
    if redis_conn:
        try:
            redis_info = redis_conn.info()
            health_status['services']['redis'] = {
                'status': 'healthy',
                'version': redis_info.get('redis_version'),
                'memory_used': redis_info.get('used_memory_human'),
                'connected_clients': redis_info.get('connected_clients'),
                'uptime_seconds': redis_info.get('uptime_in_seconds')
            }
        except Exception as e:
            health_status['services']['redis'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            overall_healthy = False
    else:
        health_status['services']['redis'] = {
            'status': 'unhealthy',
            'error': 'Could not connect to Redis'
        }
        overall_healthy = False

    # Check Celery Worker
    try:
        from app.services.background_processor import celery_app
        inspect = celery_app.control.inspect()
        stats = inspect.stats()

        if stats:
            worker_count = len(stats)
            health_status['services']['celery_worker'] = {
                'status': 'healthy',
                'active_workers': worker_count,
                'workers': list(stats.keys())
            }
        else:
            health_status['services']['celery_worker'] = {
                'status': 'unhealthy',
                'error': 'No active workers found'
            }
            overall_healthy = False
    except Exception as e:
        health_status['services']['celery_worker'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
        overall_healthy = False

    # System Resources
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        health_status['services']['system'] = {
            'status': 'healthy',
            'cpu_percent': cpu_percent,
            'memory': {
                'total': memory.total,
                'available': memory.available,
                'percent': memory.percent
            },
            'disk': {
                'total': disk.total,
                'free': disk.free,
                'percent': (disk.used / disk.total) * 100
            }
        }
    except Exception as e:
        health_status['services']['system'] = {
            'status': 'warning',
            'error': str(e)
        }

    if not overall_healthy:
        health_status['overall_status'] = 'unhealthy'
        return jsonify(health_status), 503

    return jsonify(health_status)


@admin_bp.route('/jobs', methods=['GET'])
@require_auth
@admin_required
def get_processing_jobs():
    """Get all processing jobs with status and metrics"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        status_filter = request.args.get('status')

        # Build query
        query = ProcessingJob.query

        if status_filter:
            query = query.filter(ProcessingJob.status == status_filter)

        # Get paginated results
        jobs = query.order_by(ProcessingJob.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Get job statistics
        stats = db.session.query(
            ProcessingJob.status,
            func.count(ProcessingJob.id).label('count')
        ).group_by(ProcessingJob.status).all()

        # Get recent activity (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_jobs = ProcessingJob.query.filter(
            ProcessingJob.created_at >= yesterday
        ).count()

        return jsonify({
            'jobs': [job.to_dict() for job in jobs.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': jobs.total,
                'pages': jobs.pages,
                'has_next': jobs.has_next,
                'has_prev': jobs.has_prev
            },
            'statistics': {
                'total_jobs': jobs.total,
                'recent_jobs_24h': recent_jobs,
                'status_breakdown': {
                    status: count for status, count in stats
                }
            }
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching processing jobs: {str(e)}")
        return jsonify({'error': 'Failed to fetch processing jobs'}), 500


@admin_bp.route('/jobs/<job_id>', methods=['GET'])
@require_auth
@admin_required
def get_processing_job_details(job_id):
    """Get detailed information about a specific processing job"""
    try:
        job = ProcessingJob.query.get_or_404(job_id)

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
                    'processing_status': file_storage.processing_status
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


@admin_bp.route('/metrics', methods=['GET'])
@require_auth
@admin_required
def get_system_metrics():
    """Get system performance metrics"""
    try:
        # Update Prometheus metrics before fetching
        from app.models.processing_job import ProcessingJob
        ProcessingJob.update_active_job_metrics()
        # Database metrics
        db_metrics = {}
        try:
            # Table sizes
            table_sizes = db.session.execute(text("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 10
            """)).fetchall()

            db_metrics['table_sizes'] = [
                {'table': row.tablename, 'size': row.size}
                for row in table_sizes
            ]

            # Connection stats
            conn_stats = db.session.execute(text("""
                SELECT
                    state,
                    COUNT(*) as count
                FROM pg_stat_activity
                GROUP BY state
            """)).fetchall()

            db_metrics['connections'] = {
                row.state: row.count for row in conn_stats
            }

        except Exception as e:
            db_metrics['error'] = str(e)

        # Redis metrics
        redis_metrics = {}
        redis_conn = get_redis_connection()
        if redis_conn:
            try:
                redis_info = redis_conn.info()
                redis_metrics = {
                    'memory_used': redis_info.get('used_memory_human'),
                    'connected_clients': redis_info.get('connected_clients'),
                    'total_commands_processed': redis_info.get('total_commands_processed'),
                    'keyspace_hits': redis_info.get('keyspace_hits'),
                    'keyspace_misses': redis_info.get('keyspace_misses')
                }
            except Exception as e:
                redis_metrics['error'] = str(e)

        # Processing job metrics
        job_metrics = {}
        try:
            # Jobs by status in last 24 hours
            yesterday = datetime.utcnow() - timedelta(days=1)
            job_stats = db.session.query(
                ProcessingJob.status,
                func.count(ProcessingJob.id).label('count')
            ).filter(
                ProcessingJob.created_at >= yesterday
            ).group_by(ProcessingJob.status).all()

            job_metrics['recent_jobs'] = {
                status: count for status, count in job_stats
            }

            # Average processing time for completed jobs
            completed_jobs = ProcessingJob.query.filter(
                ProcessingJob.status == 'completed',
                ProcessingJob.started_at.isnot(None),
                ProcessingJob.completed_at.isnot(None)
            ).all()

            if completed_jobs:
                total_time = sum([
                    (job.completed_at - job.started_at).total_seconds()
                    for job in completed_jobs
                ])
                job_metrics['avg_processing_time_seconds'] = total_time / len(completed_jobs)

        except Exception as e:
            job_metrics['error'] = str(e)

        return jsonify({
            'timestamp': datetime.utcnow().isoformat(),
            'database': db_metrics,
            'redis': redis_metrics,
            'processing_jobs': job_metrics
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching system metrics: {str(e)}")
        return jsonify({'error': 'Failed to fetch system metrics'}), 500


@admin_bp.route('/containers', methods=['GET'])
@require_auth
@admin_required
def get_container_status():
    """Get Docker container status (if running in Docker)"""
    try:
        # This would typically use Docker API or docker-compose ps
        # For now, we'll return basic info about the current container
        container_info = {
            'flask_api': {
                'status': 'running',
                'container_id': os.environ.get('HOSTNAME', 'unknown'),
                'environment': os.environ.get('FLASK_ENV', 'unknown')
            }
        }

        # Check if we can reach other services
        services_to_check = [
            ('postgres', os.environ.get('DATABASE_URL', '')),
            ('redis', os.environ.get('REDIS_URL', ''))
        ]

        for service_name, service_url in services_to_check:
            try:
                if service_name == 'postgres':
                    # Test database connection
                    db.session.execute(text('SELECT 1'))
                    container_info[service_name] = {'status': 'healthy'}
                elif service_name == 'redis':
                    # Test Redis connection
                    redis_conn = get_redis_connection()
                    if redis_conn:
                        redis_conn.ping()
                        container_info[service_name] = {'status': 'healthy'}
                    else:
                        container_info[service_name] = {'status': 'unhealthy'}
            except Exception as e:
                container_info[service_name] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }

        return jsonify({
            'timestamp': datetime.utcnow().isoformat(),
            'containers': container_info
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching container status: {str(e)}")
        return jsonify({'error': 'Failed to fetch container status'}), 500


@admin_bp.route('/metrics/refresh', methods=['POST'])
@require_auth
@admin_required
def refresh_metrics():
    """Manually refresh all Prometheus metrics"""
    try:
        from app.models.processing_job import ProcessingJob
        from app.services.metrics_service import MetricsService

        # Update processing job metrics
        ProcessingJob.update_active_job_metrics()

        # Update Celery queue metrics
        redis_conn = get_redis_connection()
        if redis_conn:
            try:
                from app.services.background_processor import celery_app
                inspect = celery_app.control.inspect()

                # Get active and reserved tasks
                active_tasks = inspect.active() or {}
                reserved_tasks = inspect.reserved() or {}

                # Count total tasks
                total_active = sum(len(tasks) for tasks in active_tasks.values())
                total_waiting = sum(len(tasks) for tasks in reserved_tasks.values())

                MetricsService.update_celery_queue_metrics(total_waiting, total_active)

            except Exception as e:
                current_app.logger.warning(f"Could not update Celery metrics: {str(e)}")

        # Update database connection metrics
        try:
            pool = db.engine.pool
            if hasattr(pool, 'checkedout'):
                active_connections = pool.checkedout()
                MetricsService.update_database_connections(active_connections)
        except Exception as e:
            current_app.logger.warning(f"Could not update DB connection metrics: {str(e)}")

        return jsonify({
            'status': 'success',
            'message': 'Metrics refreshed successfully',
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error refreshing metrics: {str(e)}")
        return jsonify({'error': 'Failed to refresh metrics'}), 500

@admin_bp.route('/alerts/webhook', methods=['POST'])
@require_auth
@admin_required
def handle_alert_webhook():
    """Handle AlertManager webhook notifications"""
    try:
        from flask import request
        alert_data = request.get_json()

        # Log the alert for now (can be enhanced to store in DB or forward to external systems)
        current_app.logger.info(f"Received alert: {alert_data}")

        # Here you could:
        # 1. Store alerts in database for admin dashboard
        # 2. Forward to external notification systems
        # 3. Trigger automated responses

        return jsonify({
            'status': 'success',
            'message': 'Alert received',
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error handling alert webhook: {str(e)}")
        return jsonify({'error': 'Failed to handle alert'}), 500

# ========================================
# USER MANAGEMENT ENDPOINTS
# ========================================

@admin_bp.route('/users', methods=['GET'])
@require_auth
@admin_required
def get_all_users():
    """Get all users with pagination and filtering"""
    from flask import request
    from app.models.user import User


    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        role_filter = request.args.get('role')
        active_filter = request.args.get('active')
        search = request.args.get('search', '').strip()

        # Build query
        query = User.query

        # Apply filters
        if role_filter:
            query = query.filter(User.role == role_filter)

        if active_filter is not None:
            is_active = active_filter.lower() == 'true'
            query = query.filter(User.is_active == is_active)

        if search:
            query = query.filter(
                db.or_(
                    User.name.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%')
                )
            )

        # Get paginated results
        users = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Get user statistics
        total_users = User.query.count()
        active_users = User.query.filter(User.is_active == True).count()
        admin_users = User.query.filter(User.role == 'admin').count()

        return jsonify({
            'users': [user.to_dict() for user in users.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': users.total,
                'pages': users.pages,
                'has_next': users.has_next,
                'has_prev': users.has_prev
            },
            'statistics': {
                'total_users': total_users,
                'active_users': active_users,
                'admin_users': admin_users,
                'inactive_users': total_users - active_users
            }
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching users: {str(e)}")
        return jsonify({'error': 'Failed to fetch users'}), 500

@admin_bp.route('/users/<user_id>', methods=['GET'])
@require_auth
@admin_required
def get_user_details(user_id):
    """Get detailed information about a specific user"""
    from app.models.user import User


    try:
        user = User.query.get_or_404(user_id)

        # Get user activity statistics
        file_count = FileStorage.query.filter_by(user_id=user_id).count()
        job_count = ProcessingJob.query.filter_by(user_id=user_id).count()

        # Get recent activity
        recent_jobs = ProcessingJob.query.filter_by(user_id=user_id)\
            .order_by(ProcessingJob.created_at.desc())\
            .limit(5)\
            .all()

        user_data = user.to_dict()
        user_data.update({
            'activity_statistics': {
                'files_uploaded': file_count,
                'processing_jobs': job_count,
                'recent_jobs': [job.to_dict() for job in recent_jobs]
            }
        })

        return jsonify({'user': user_data})

    except Exception as e:
        current_app.logger.error(f"Error fetching user details: {str(e)}")
        return jsonify({'error': 'Failed to fetch user details'}), 500

@admin_bp.route('/users/<user_id>/status', methods=['PATCH'])
@require_auth
@admin_required
def update_user_status(user_id):
    """Activate or deactivate a user account"""
    from flask import request
    from app.models.user import User


    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()

        if 'is_active' not in data:
            return jsonify({'error': 'is_active field is required'}), 400

        old_status = user.is_active
        user.is_active = data['is_active']

        db.session.commit()

        # Log the action
        current_app.logger.info(
            f"User {user.email} status changed from {old_status} to {user.is_active}"
        )

        return jsonify({
            'message': 'User status updated successfully',
            'user': user.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user status: {str(e)}")
        return jsonify({'error': 'Failed to update user status'}), 500

@admin_bp.route('/users/<user_id>/role', methods=['PATCH'])
@require_auth
@admin_required
def update_user_role(user_id):
    """Update a user's role"""
    from flask import request
    from app.models.user import User


    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()

        if 'role' not in data:
            return jsonify({'error': 'role field is required'}), 400

        valid_roles = ['user', 'admin']
        if data['role'] not in valid_roles:
            return jsonify({'error': f'Invalid role. Must be one of: {valid_roles}'}), 400

        old_role = user.role
        user.role = data['role']

        db.session.commit()

        # Log the action
        current_app.logger.info(
            f"User {user.email} role changed from {old_role} to {user.role}"
        )

        return jsonify({
            'message': 'User role updated successfully',
            'user': user.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user role: {str(e)}")
        return jsonify({'error': 'Failed to update user role'}), 500

@admin_bp.route('/access-codes', methods=['POST'])
@require_auth
@admin_required
def generate_access_code():
    """Generate a new access code for user invitation"""
    from flask import request
    from app.models.access_code import AccessCode
    from datetime import datetime, timedelta
    import secrets
    import string

    try:
        data = request.get_json() or {}

        # Generate secure 12-character access code
        code_length = 12
        access_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                            for _ in range(code_length))

        # Check if code already exists (very unlikely but possible)
        while AccessCode.query.filter_by(code=access_code).first():
            access_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                                for _ in range(code_length))

        # Set expiration to 24 hours from now
        expiry_hours = 24
        expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)

        # Create access code record
        new_access_code = AccessCode(
            code=access_code,
            is_used=False,
            expires_at=expires_at
        )

        db.session.add(new_access_code)
        db.session.commit()

        current_app.logger.info(f"Generated access code {access_code} (expires in {expiry_hours}h)")

        return jsonify({
            'access_code': access_code,
            'expires_at': expires_at.isoformat(),
            'expiry_hours': expiry_hours,
            'invitation_url': f"{request.host_url}auth/signup?access_code={access_code}",
            'message': 'Access code generated successfully'
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating access code: {str(e)}")
        return jsonify({'error': 'Failed to generate access code'}), 500

@admin_bp.route('/access-codes/validate', methods=['POST'])
def validate_access_code():
    """Validate an access code for user signup"""
    from flask import request
    from app.models.user import User

    try:
        data = request.get_json()
        access_code = data.get('access_code')
        email = data.get('email')

        if not access_code:
            return jsonify({'valid': False, 'error': 'Access code is required'}), 400

        # Check if access code exists and is unused
        temp_user = User.query.filter_by(access_code=access_code, is_active=False).first()

        if not temp_user:
            return jsonify({'valid': False, 'error': 'Invalid or expired access code'}), 400

        # If email is provided, update the temp user record
        if email and temp_user.email.startswith('pending-'):
            temp_user.email = email
            temp_user.name = email.split('@')[0].title()  # Use email username as name
            db.session.commit()

        return jsonify({
            'valid': True,
            'message': 'Access code is valid'
        })

    except Exception as e:
        current_app.logger.error(f"Error validating access code: {str(e)}")
        return jsonify({'valid': False, 'error': 'Failed to validate access code'}), 500


# ========================================
# INVOICE CRUD ENDPOINTS
# ========================================

@admin_bp.route('/invoices', methods=['POST'])
@require_auth
@admin_required
def create_invoice():
    """Create a new invoice"""
    from app.models.invoice import Invoice, InvoiceLineItem
    from app.models.audit_log import AuditLog
    from app.utils.auth import get_current_user
    current_user = get_current_user()

    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('invoice_number'):
            return jsonify({'error': 'invoice_number is required'}), 400
        if not data.get('invoice_date'):
            return jsonify({'error': 'invoice_date is required'}), 400
        if not data.get('total_amount'):
            return jsonify({'error': 'total_amount is required'}), 400

        # Check for duplicate invoice number
        existing = Invoice.query.filter_by(invoice_number=data['invoice_number']).first()
        if existing:
            return jsonify({'error': 'Invoice number already exists'}), 400

        # Create invoice
        invoice = Invoice(
            sales_order_id=data.get('sales_order_id'),
            invoice_number=data['invoice_number'],
            invoice_date=data['invoice_date'],
            due_date=data.get('due_date'),
            ship_date=data.get('ship_date'),
            customer_id=data.get('customer_id'),
            salesperson_id=data.get('salesperson_id'),
            territory_id=data.get('territory_id'),
            account_number=data.get('account_number'),
            po_number=data.get('po_number'),
            subtotal=data.get('subtotal', 0),
            tax_amount=data.get('tax_amount', 0),
            freight=data.get('freight', 0),
            shipping_handling=data.get('shipping_handling', 0),
            total_amount=data['total_amount'],
            payment_status=data.get('payment_status', 'unpaid'),
            notes=data.get('notes')
        )

        db.session.add(invoice)
        db.session.flush()  # Get invoice ID

        # Add line items if provided
        if data.get('line_items'):
            for idx, item_data in enumerate(data['line_items']):
                line_item = InvoiceLineItem(
                    invoice_id=invoice.id,
                    line_number=idx + 1,
                    product_id=item_data.get('product_id'),
                    item_number=item_data.get('item_number'),
                    description=item_data['description'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    unit_price_discount=item_data.get('unit_price_discount', 0),
                    line_total=item_data['line_total']
                )
                db.session.add(line_item)

        # Create audit log
        audit = AuditLog(
            table_name='invoices',
            record_id=invoice.id,
            action='create',
            new_values=invoice.to_dict(),
            changed_by=current_user.email,
            change_reason=data.get('change_reason', 'Admin invoice creation')
        )
        db.session.add(audit)

        db.session.commit()

        return jsonify({
            'message': 'Invoice created successfully',
            'invoice': invoice.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating invoice: {str(e)}")
        return jsonify({'error': 'Failed to create invoice'}), 500


@admin_bp.route('/invoices/<invoice_id>', methods=['PUT'])
@require_auth
@admin_required
def update_invoice(invoice_id):
    """Update an existing invoice"""
    from app.models.invoice import Invoice
    from app.models.audit_log import AuditLog
    from app.utils.auth import get_current_user
    current_user = get_current_user()

    try:
        invoice = Invoice.query.get_or_404(invoice_id)
        data = request.get_json()

        # Store old values for audit
        old_values = invoice.to_dict()

        # Update fields
        updatable_fields = [
            'invoice_date', 'due_date', 'ship_date', 'customer_id', 'salesperson_id',
            'territory_id', 'account_number', 'po_number', 'subtotal', 'tax_amount',
            'freight', 'shipping_handling', 'total_amount', 'payment_status', 'notes',
            'special_instructions'
        ]

        changed_fields = []
        for field in updatable_fields:
            if field in data and getattr(invoice, field) != data[field]:
                setattr(invoice, field, data[field])
                changed_fields.append(field)

        if changed_fields:
            # Create audit log
            audit = AuditLog(
                table_name='invoices',
                record_id=invoice.id,
                action='update',
                old_values=old_values,
                new_values=invoice.to_dict(),
                changed_fields=changed_fields,
                changed_by=current_user.email,
                change_reason=data.get('change_reason', 'Admin invoice update')
            )
            db.session.add(audit)

        db.session.commit()

        return jsonify({
            'message': 'Invoice updated successfully',
            'invoice': invoice.to_dict(),
            'changed_fields': changed_fields
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating invoice: {str(e)}")
        return jsonify({'error': 'Failed to update invoice'}), 500


@admin_bp.route('/invoices/<invoice_id>', methods=['DELETE'])
@require_auth
@admin_required
def delete_invoice(invoice_id):
    """Delete an invoice (soft delete or hard delete based on parameter)"""
    from app.models.invoice import Invoice
    from app.models.audit_log import AuditLog
    from app.utils.auth import get_current_user
    current_user = get_current_user()

    try:
        invoice = Invoice.query.get_or_404(invoice_id)
        soft_delete = request.args.get('soft', 'true').lower() == 'true'

        # Store old values for audit
        old_values = invoice.to_dict()

        if soft_delete:
            # Mark as deleted but keep in database
            invoice.is_active = False
            action = 'soft_delete'
        else:
            # Hard delete
            db.session.delete(invoice)
            action = 'delete'

        # Create audit log
        audit = AuditLog(
            table_name='invoices',
            record_id=invoice.id,
            action=action,
            old_values=old_values,
            changed_by=current_user.email,
            change_reason=request.args.get('reason', 'Admin invoice deletion')
        )
        db.session.add(audit)

        db.session.commit()

        return jsonify({
            'message': f"Invoice {'soft deleted' if soft_delete else 'deleted'} successfully"
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting invoice: {str(e)}")
        return jsonify({'error': 'Failed to delete invoice'}), 500


@admin_bp.route('/invoices/<invoice_id>/replace', methods=['POST'])
@require_auth
@admin_required
def replace_invoice_file(invoice_id):
    """Replace an invoice with a new file upload"""
    from app.models.invoice import Invoice
    from app.models.audit_log import AuditLog
    from app.models.file_storage import FileStorage
    from app.utils.auth import get_current_user
    current_user = get_current_user()

    try:
        invoice = Invoice.query.get_or_404(invoice_id)

        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400

        # Store old filename for audit
        old_filename = invoice.original_filename

        # Update invoice with new file
        invoice.original_filename = file.filename
        invoice.requires_review = True  # Mark for review since it's replaced

        # Create file storage record
        file_storage = FileStorage(
            user_id=current_user.id,
            file_name=file.filename,
            file_size=len(file.read()),
            mime_type=file.content_type,
            upload_source='admin_replace'
        )
        file.seek(0)  # Reset file pointer after reading size

        db.session.add(file_storage)

        # Create audit log
        audit = AuditLog(
            table_name='invoices',
            record_id=invoice.id,
            action='replace_file',
            old_values={'original_filename': old_filename},
            new_values={'original_filename': file.filename},
            changed_by=current_user.email,
            change_reason=request.form.get('reason', 'Admin invoice file replacement')
        )
        db.session.add(audit)

        db.session.commit()

        return jsonify({
            'message': 'Invoice file replaced successfully',
            'invoice': invoice.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error replacing invoice file: {str(e)}")
        return jsonify({'error': 'Failed to replace invoice file'}), 500


# ========================================
# AUDIT LOG & USAGE ANALYTICS ENDPOINTS
# ========================================

@admin_bp.route('/audit-log', methods=['GET'])
@require_auth
@admin_required
def get_audit_log():
    """Get change history with pagination and filtering"""
    from app.models.audit_log import AuditLog


    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        table_name = request.args.get('table')
        action = request.args.get('action')
        changed_by = request.args.get('changed_by')

        # Build query
        query = AuditLog.query

        # Apply filters
        if table_name:
            query = query.filter(AuditLog.table_name == table_name)
        if action:
            query = query.filter(AuditLog.action == action)
        if changed_by:
            query = query.filter(AuditLog.changed_by.ilike(f'%{changed_by}%'))

        # Get paginated results
        audit_logs = query.order_by(AuditLog.changed_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return jsonify({
            'audit_logs': [log.to_dict() for log in audit_logs.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': audit_logs.total,
                'pages': audit_logs.pages,
                'has_next': audit_logs.has_next,
                'has_prev': audit_logs.has_prev
            }
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching audit log: {str(e)}")
        return jsonify({'error': 'Failed to fetch audit log'}), 500


@admin_bp.route('/usage-analytics', methods=['GET'])
@require_auth
@admin_required
def get_usage_analytics():
    """Get usage analytics data"""
    from app.models.usage_analytics import UsageAnalytics

    try:
        # Get date range
        days = request.args.get('days', 30, type=int)
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get page view summary
        page_views = db.session.query(
            UsageAnalytics.route,
            func.count(UsageAnalytics.id).label('views'),
            func.count(func.distinct(UsageAnalytics.user_id)).label('unique_users'),
            func.avg(UsageAnalytics.duration_seconds).label('avg_duration')
        ).filter(
            UsageAnalytics.viewed_at >= cutoff_date
        ).group_by(
            UsageAnalytics.route
        ).order_by(
            func.count(UsageAnalytics.id).desc()
        ).all()

        # Get daily active users
        daily_active = db.session.query(
            func.date(UsageAnalytics.viewed_at).label('date'),
            func.count(func.distinct(UsageAnalytics.user_id)).label('active_users')
        ).filter(
            UsageAnalytics.viewed_at >= cutoff_date
        ).group_by(
            func.date(UsageAnalytics.viewed_at)
        ).order_by(
            func.date(UsageAnalytics.viewed_at)
        ).all()

        # Get top users by activity
        top_users = db.session.query(
            UsageAnalytics.user_id,
            func.count(UsageAnalytics.id).label('page_views'),
            func.sum(UsageAnalytics.duration_seconds).label('total_time')
        ).filter(
            UsageAnalytics.viewed_at >= cutoff_date,
            UsageAnalytics.user_id.isnot(None)
        ).group_by(
            UsageAnalytics.user_id
        ).order_by(
            func.count(UsageAnalytics.id).desc()
        ).limit(10).all()

        return jsonify({
            'page_views': [
                {
                    'route': pv.route,
                    'views': pv.views,
                    'unique_users': pv.unique_users,
                    'avg_duration_seconds': int(pv.avg_duration) if pv.avg_duration else 0
                }
                for pv in page_views
            ],
            'daily_active_users': [
                {
                    'date': str(da.date),
                    'active_users': da.active_users
                }
                for da in daily_active
            ],
            'top_users': [
                {
                    'user_id': str(tu.user_id),
                    'page_views': tu.page_views,
                    'total_time_seconds': int(tu.total_time) if tu.total_time else 0
                }
                for tu in top_users
            ],
            'period_days': days
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching usage analytics: {str(e)}")
        return jsonify({'error': 'Failed to fetch usage analytics'}), 500
