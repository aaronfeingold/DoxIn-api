"""
Database auto-initialization utilities
Handles automatic table creation and admin user setup on startup
"""
import os
from sqlalchemy import text
from flask import current_app
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, Account


def check_database_connection():
    """Test if database connection is working"""
    try:
        db.session.execute(text('SELECT 1'))
        return True
    except Exception as e:
        current_app.logger.error(f"Database connection failed: {e}")
        return False


def check_tables_exist():
    """Check if database tables exist"""
    try:
        # Check if users table exists by trying to query it
        db.session.execute(text("SELECT 1 FROM users LIMIT 1"))
        return True
    except Exception:
        # Table doesn't exist or other error
        return False


def create_database_tables():
    """Create all database tables"""
    try:
        current_app.logger.info("Creating database tables...")
        db.create_all()
        current_app.logger.info("Database tables created successfully")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to create database tables: {e}")
        return False


def check_admin_exists():
    """Check if at least one admin user exists"""
    try:
        admin_user = User.query.filter_by(role='admin').first()
        return admin_user is not None
    except Exception:
        # Table might not exist yet
        return False


def create_first_admin():
    """Create the first admin user with password-based login"""
    try:
        # Get admin details from environment or use defaults
        admin_email = os.environ.get('INITIAL_ADMIN_EMAIL', 'admin@case-study.local')
        admin_name = os.environ.get('INITIAL_ADMIN_NAME', 'System Administrator')
        default_password = os.environ.get('INITIAL_ADMIN_PASSWORD', 'admin123')

        # Check if user already exists
        existing_user = User.query.filter_by(email=admin_email).first()
        if existing_user:
            if existing_user.role != 'admin':
                existing_user.role = 'admin'
                db.session.commit()
                current_app.logger.info(f"Updated existing user {admin_email} to admin role")
            else:
                current_app.logger.info(f"Admin user already exists: {admin_email}")
            return True

        # Create new admin user (Better Auth compatible)
        admin_user = User(
            email=admin_email,
            name=admin_name,
            role='admin',
            is_active=True,
            email_verified=True  # Auto-verify admin email
        )

        db.session.add(admin_user)
        db.session.flush()  # Get the user ID

        # Create credential account with password (Better Auth pattern)
        admin_account = Account(
            user_id=admin_user.id,
            account_id=admin_email,  # Use email as account_id for credentials provider
            provider_id='credential',  # Better Auth credential provider
            password=generate_password_hash(default_password)
        )

        db.session.add(admin_account)
        db.session.commit()

        current_app.logger.info(
            f"Created first admin user: {admin_email} (password: {default_password})"
        )
        current_app.logger.warning(
            f"SECURITY: Change the default admin password! Email: {admin_email}"
        )
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to create admin user: {e}")
        db.session.rollback()
        return False


def auto_initialize_database():
    """
    Auto-initialize database on startup
    - Check database connection
    - Create tables if needed
    - Ensure at least one admin user exists
    """
    current_app.logger.info("Checking database initialization...")

    # Check database connection
    if not check_database_connection():
        current_app.logger.error("Database connection failed")
        return False

    current_app.logger.info("Database connection successful")

    # Check if tables exist
    tables_exist = check_tables_exist()

    if not tables_exist:
        current_app.logger.info("First run detected - creating database tables...")
        if not create_database_tables():
            return False
    else:
        current_app.logger.info("Database tables exist")

    # Ensure admin user exists
    if not check_admin_exists():
        current_app.logger.info("No admin user found - creating first admin...")
        if not create_first_admin():
            return False
    else:
        current_app.logger.info("Admin user found")

    current_app.logger.info("Database initialization complete - system ready!")
    return True
