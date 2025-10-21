"""
Health check routes
"""
from flask import Blueprint, jsonify, Response
from app import db
from app.utils.routes_helpers import get_redis_connection
from sqlalchemy import text
from app.services.metrics_service import metrics_endpoint, MetricsService

health_bp = Blueprint('health', __name__)


@health_bp.route('/', methods=['GET'])
def health_check():
    """Basic health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'case-study-invoice-extraction',
        'version': '1.0.0'
    })


@health_bp.route('/database', methods=['GET'])
def database_health():
    """Database connectivity health check"""
    try:
        # Test database connection
        db.session.execute(text('SELECT 1'))

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'message': 'Database connection successful'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 503


@health_bp.route('/detailed', methods=['GET'])
def detailed_health():
    """Detailed health check with component status"""
    health_status = {
        'status': 'healthy',
        'components': {}
    }

    overall_healthy = True

    # Check database
    try:
        db.session.execute(text('SELECT 1'))
        health_status['components']['database'] = {
            'status': 'healthy',
            'message': 'Connected'
        }
    except Exception as e:
        health_status['components']['database'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
        overall_healthy = False

    # Check pgvector extension (if available)
    try:
        result = db.session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
        if result.rowcount > 0:
            health_status['components']['pgvector'] = {
                'status': 'healthy',
                'message': 'Extension available'
            }
        else:
            health_status['components']['pgvector'] = {
                'status': 'warning',
                'message': 'Extension not installed'
            }
    except Exception as e:
        health_status['components']['pgvector'] = {
            'status': 'unknown',
            'error': str(e)
        }

    # Check Redis connection
    try:
        r = get_redis_connection()
        if r:
            r.ping()
            health_status['components']['redis'] = {
                'status': 'healthy',
                'message': 'Connected'
            }
        else:
            raise Exception("Could not establish Redis connection")
    except Exception as e:
        health_status['components']['redis'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
        overall_healthy = False

    # Update database connection metrics
    try:
        # Get database connection pool info (if using SQLAlchemy pool)
        pool = db.engine.pool
        if hasattr(pool, 'checkedout'):
            active_connections = pool.checkedout()
            MetricsService.update_database_connections(active_connections)
    except Exception:
        pass  # Skip if connection pooling info not available

    if not overall_healthy:
        health_status['status'] = 'unhealthy'
        return jsonify(health_status), 503

    return jsonify(health_status)


@health_bp.route('/metrics', methods=['GET'])
def prometheus_metrics():
    """Prometheus metrics endpoint"""
    return Response(metrics_endpoint(), mimetype='text/plain')
