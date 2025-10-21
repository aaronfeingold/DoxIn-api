"""
Prometheus metrics service for Flask application
"""
import time
import functools
from flask import request, g
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest
from prometheus_client.core import REGISTRY

# Initialize metrics
REQUEST_COUNT = Counter(
    'flask_http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'flask_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

REQUEST_EXCEPTIONS = Counter(
    'flask_http_request_exceptions_total',
    'Total number of HTTP request exceptions',
    ['method', 'endpoint', 'exception']
)

ACTIVE_REQUESTS = Gauge(
    'flask_http_requests_active',
    'Number of active HTTP requests'
)

# Business metrics
INVOICES_PROCESSED = Counter(
    'invoices_processed_total',
    'Total number of invoices processed',
    ['status']
)

PROCESSING_JOB_DURATION = Histogram(
    'processing_job_duration_seconds',
    'Time spent processing jobs',
    ['job_type']
)

PROCESSING_JOBS_ACTIVE = Gauge(
    'processing_jobs_active',
    'Number of active processing jobs',
    ['job_type', 'status']
)

EXTRACTION_ACCURACY = Histogram(
    'extraction_accuracy_score',
    'Accuracy scores for data extraction',
    ['extraction_type']
)

DATABASE_CONNECTIONS = Gauge(
    'database_connections_active',
    'Number of active database connections'
)

CELERY_TASKS_WAITING = Gauge(
    'celery_tasks_waiting',
    'Number of tasks waiting in Celery queue'
)

CELERY_TASKS_ACTIVE = Gauge(
    'celery_tasks_active',
    'Number of active Celery tasks'
)

# Application info
APP_INFO = Info(
    'flask_app_info',
    'Flask application information'
)


class MetricsService:
    """Service for managing Prometheus metrics"""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize metrics service with Flask app"""
        self.app = app

        # Set application info
        APP_INFO.info({
            'version': app.config.get('VERSION', '1.0.0'),
            'environment': app.config.get('ENVIRONMENT', 'development')
        })

        # Register before/after request handlers
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.teardown_request(self._teardown_request)

    def _before_request(self):
        """Track request start time and increment active requests"""
        g.start_time = time.time()
        ACTIVE_REQUESTS.inc()

    def _after_request(self, response):
        """Track request completion metrics"""
        try:
            # Calculate request duration
            request_duration = time.time() - g.start_time

            # Get endpoint name (remove URL parameters)
            endpoint = request.endpoint or 'unknown'
            method = request.method
            status_code = str(response.status_code)

            # Update metrics
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()

            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint
            ).observe(request_duration)

        except Exception as e:
            # Don't let metrics tracking break the request
            app.logger.error(f"Error tracking metrics: {e}")

        return response

    def _teardown_request(self, exception):
        """Handle request teardown and exceptions"""
        try:
            ACTIVE_REQUESTS.dec()

            # Track exceptions
            if exception:
                endpoint = request.endpoint or 'unknown'
                method = request.method
                exception_type = type(exception).__name__

                REQUEST_EXCEPTIONS.labels(
                    method=method,
                    endpoint=endpoint,
                    exception=exception_type
                ).inc()
        except Exception as e:
            # Don't let metrics tracking break the request
            if self.app:
                self.app.logger.error(f"Error in metrics teardown: {e}")

    @staticmethod
    def track_invoice_processing(status):
        """Track invoice processing completion"""
        INVOICES_PROCESSED.labels(status=status).inc()

    @staticmethod
    def track_processing_job_duration(job_type, duration):
        """Track processing job duration"""
        PROCESSING_JOB_DURATION.labels(job_type=job_type).observe(duration)

    @staticmethod
    def update_active_jobs(job_type, status, count):
        """Update active processing jobs gauge"""
        PROCESSING_JOBS_ACTIVE.labels(job_type=job_type, status=status).set(count)

    @staticmethod
    def track_extraction_accuracy(extraction_type, accuracy):
        """Track extraction accuracy scores"""
        EXTRACTION_ACCURACY.labels(extraction_type=extraction_type).observe(accuracy)

    @staticmethod
    def update_database_connections(count):
        """Update active database connections"""
        DATABASE_CONNECTIONS.set(count)

    @staticmethod
    def update_celery_queue_metrics(waiting_count, active_count):
        """Update Celery queue metrics"""
        CELERY_TASKS_WAITING.set(waiting_count)
        CELERY_TASKS_ACTIVE.set(active_count)


def metrics_endpoint():
    """Generate Prometheus metrics endpoint response"""
    return generate_latest(REGISTRY)


def track_processing_time(job_type):
    """Decorator to track processing time for functions"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                MetricsService.track_processing_job_duration(job_type, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                MetricsService.track_processing_job_duration(job_type, duration)
                raise
        return wrapper
    return decorator


# Initialize global metrics service instance
metrics_service = MetricsService()
