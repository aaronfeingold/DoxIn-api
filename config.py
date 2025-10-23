"""
Flask application configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    JWT_SECRET = os.environ.get('JWT_SECRET') or 'dev-jwt-secret-change-in-production'
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
    JWT_EXP_MINUTES = int(os.environ.get('JWT_EXP_MINUTES', 15))

    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://api_user:password@localhost:5433/api_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Base engine options
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'echo': False  # Set to True for SQL debugging
    }

    # Detect Neon DB and apply optimizations
    @classmethod
    def is_neon_db(cls):
        """Check if using Neon database"""
        db_url = os.environ.get('DATABASE_URL', '')
        return 'neon.tech' in db_url or 'neon.db' in db_url

    @classmethod
    def get_engine_options(cls):
        """Get optimized engine options based on database type"""
        options = cls.SQLALCHEMY_ENGINE_OPTIONS.copy()

        if cls.is_neon_db():
            # Neon DB optimizations for serverless environment
            options.update({
                'pool_size': 5,          # Smaller pool for serverless
                'max_overflow': 0,       # No overflow for predictable connections
                'pool_timeout': 10,      # Shorter timeout for serverless
                'pool_recycle': 3600,    # Longer recycle for stable connections
                'connect_args': {
                    'sslmode': 'require',
                    'connect_timeout': 10,
                    'application_name': 'case-study-invoice-app'
                }
            })
        else:
            # Local/traditional PostgreSQL optimizations
            options.update({
                'pool_size': 10,
                'max_overflow': 5,
                'pool_timeout': 30,
            })

        return options

    # File Upload Configuration
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or './uploads'
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

    # AI/LLM Configuration
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
    EMBEDDING_DIMENSIONS = int(os.environ.get('EMBEDDING_DIMENSIONS', 1536))
    DEFAULT_LLM_MODEL = os.environ.get('DEFAULT_LLM_MODEL', 'gpt-4o')
    CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', 0.75))

    # Processing Configuration
    BATCH_PROCESSING_SIZE = int(os.environ.get('BATCH_PROCESSING_SIZE', 10))

    # CORS Configuration
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
    # Parse ALLOWED_ORIGINS as comma-separated list (used in development mode)
    ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get('ALLOWED_ORIGINS', '').split(',')
        if origin.strip()
    ]

    # Background Processing (Optional)
    REDIS_URL = os.environ.get('REDIS_URL')
    REDIS_SESSION_DB = int(os.environ.get('REDIS_SESSION_DB', 2))
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)

    # Application Metadata
    SEM_VER = os.environ.get('SEM_VER', '0.0.0')
    ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

    # Monitoring Configuration
    METRICS_ENABLED = os.environ.get('METRICS_ENABLED', 'true').lower() == 'true'
    PROMETHEUS_METRICS_PATH = os.environ.get('PROMETHEUS_METRICS_PATH', '/metrics')

    @classmethod
    def validate_ai_api_keys(cls):
        """
        Validate that at least one AI API key is configured.
        Prints a warning if no keys are found.

        Returns:
            bool: True if at least one API key is configured, False otherwise
        """
        has_openai = bool(os.getenv('OPENAI_API_KEY'))
        has_anthropic = bool(os.getenv('ANTHROPIC_API_KEY'))

        if not has_openai and not has_anthropic:
            print("Warning: No AI API keys found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variables.")
            return False

        return True


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

    @classmethod
    def get_engine_options(cls):
        """Development-specific engine options"""
        options = super().get_engine_options()
        options['echo'] = True  # Enable SQL logging in development
        return options


# Set engine options as class attribute
DevelopmentConfig.SQLALCHEMY_ENGINE_OPTIONS = DevelopmentConfig.get_engine_options()


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

    @classmethod
    def get_engine_options(cls):
        """Production-specific engine options"""
        options = super().get_engine_options()

        if cls.is_neon_db():
            # Neon DB production settings
            options.update({
                'pool_size': 8,           # Optimized for Neon's connection limits
                'max_overflow': 0,        # Strict connection control
                'pool_timeout': 15,       # Reasonable timeout for production
            })
        else:
            # Traditional PostgreSQL production settings
            options.update({
                'pool_size': 20,
                'max_overflow': 0,
                'pool_timeout': 30,
            })

        return options


# Set engine options as class attribute
ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS = ProductionConfig.get_engine_options()


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:password@localhost:5432/case_study_test'


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
