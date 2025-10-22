"""
Flask application factory
"""
import os
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

# API Configuration
API_VERSION = 'v1'

# Initialize extensions
db = SQLAlchemy()
socketio = SocketIO()


def create_app(config_name=None):
    """Create Flask application with configuration"""
    app = Flask(__name__)

    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')

    from config import config
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)

    # Initialize metrics service
    from app.services.metrics_service import metrics_service
    metrics_service.init_app(app)

    # Initialize SocketIO with CORS
    # In development, allow multiple localhost origins for flexibility with proxies
    cors_origins = app.config['FRONTEND_URL']
    if app.config.get('DEBUG', False) or app.config.get('ENV') == 'development':
        # Allow various localhost ports (actual server + proxies) + network access
        cors_origins = [
            'http://localhost:3000',
            'http://localhost:65228',
            'http://127.0.0.1:3000',
            'http://127.0.0.1:65228',
            'http://10.0.0.27:3000',
            'http://10.0.0.27:65228',
        ]

    socketio.init_app(
        app,
        cors_allowed_origins=cors_origins,
        async_mode='threading',
        logger=True,
        engineio_logger=True,
        cors_credentials=True
    )

    # Configure CORS for regular routes
    if app.config.get('DEBUG', False):
        # In development, allow common localhost ports + network access
        allowed_origins = [
            'http://localhost:3000',
            'http://localhost:65228',
            'http://127.0.0.1:3000',
            'http://127.0.0.1:65228',
            'http://10.0.0.27:3000',
            'http://10.0.0.27:65228',
        ]
    else:
        allowed_origins = [app.config['FRONTEND_URL']]

    CORS(app, origins=allowed_origins, supports_credentials=True)

    # Create upload directory
    upload_dir = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # Auto-initialize database on startup
    with app.app_context():
        from app.utils.db_init import auto_initialize_database
        auto_initialize_database()

    # Register blueprints with API versioning
    from app.routes.invoices import invoices_bp
    from app.routes.health import health_bp
    from app.routes.admin import admin_bp
    from app.routes.reports import reports_bp
    from app.routes.jobs import jobs_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.auth import auth_bp

    # API v1 routes
    api_prefix = f'/api/{API_VERSION}'
    app.register_blueprint(health_bp, url_prefix=f'{api_prefix}/health')
    app.register_blueprint(admin_bp, url_prefix=f'{api_prefix}/admin')
    app.register_blueprint(invoices_bp, url_prefix=f'{api_prefix}/invoices')
    app.register_blueprint(reports_bp, url_prefix=f'{api_prefix}/reports')
    app.register_blueprint(jobs_bp, url_prefix=f'{api_prefix}/jobs')
    app.register_blueprint(dashboard_bp, url_prefix=f'{api_prefix}/dashboard')
    app.register_blueprint(auth_bp, url_prefix=f'{api_prefix}/auth')

    # Register analytics middleware
    try:
        from app.middleware.analytics import init_usage_analytics
        init_usage_analytics(app)
    except Exception as e:
        app.logger.warning(f"Usage analytics middleware not initialized: {e}")

    # Initialize WebSocket manager
    from app.services.websocket_manager import init_websocket_manager
    init_websocket_manager(socketio)

    # Initialize Redis subscriber to forward worker events to WebSocket clients
    from app.services.redis_subscriber import init_redis_subscriber
    init_redis_subscriber(socketio)

    # Initialize Celery for async processing
    try:
        from app.services.async_processor import init_celery
        init_celery(app)
    except Exception as e:
        app.logger.warning(f"Celery not initialized: {e}")

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Resource not found'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {'error': 'Internal server error'}, 500

    @app.errorhandler(413)
    def file_too_large(error):
        return {'error': 'File too large. Maximum size is 16MB.'}, 413

    return app
