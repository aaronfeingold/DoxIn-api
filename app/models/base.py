"""
Base model with common functionality
"""
import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, DateTime, func
from flask import g, has_request_context
from app import db

class BaseModel(db.Model):
    """Base model class with common fields and methods (Better Auth compatible)"""
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        """Convert model instance to dictionary"""
        result = {}
        for column in self.__table__.columns:
            # Use column.key for attribute access to support differing
            # Python attribute names vs database column names
            value = getattr(self, column.key)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            else:
                result[column.name] = value
        return result

    def save(self, user_email=None, reason=None):
        """Save the model instance with audit logging"""
        # Capture old values for audit
        old_values = None
        action = 'CREATE'

        if self.id:
            # This is an update - get current values from database
            existing = self.__class__.query.get(self.id)
            if existing:
                old_values = existing.to_dict()
                action = 'UPDATE'

        # Save the model
        db.session.add(self)
        db.session.flush()  # Flush to get the ID but don't commit yet

        # Create audit log entry
        self._create_audit_log(action, old_values, self.to_dict(), user_email, reason)

        # Commit everything together
        db.session.commit()
        return self

    def delete(self, user_email=None, reason=None):
        """Delete the model instance with audit logging"""
        # Capture current values before deletion
        old_values = self.to_dict()

        # Create audit log entry
        self._create_audit_log('DELETE', old_values, None, user_email, reason)

        # Delete the model
        db.session.delete(self)
        db.session.commit()

    def _create_audit_log(self, action, old_values, new_values, user_email=None, reason=None):
        """Create an audit log entry"""
        # Skip audit logging for AuditLog model itself to avoid recursion
        if self.__class__.__name__ == 'AuditLog':
            return

        try:
            # Import here to avoid circular imports
            from app.models.audit_log import AuditLog

            # Get user email from request context or parameter
            if not user_email and has_request_context():
                user_email = getattr(g, 'current_user_email', None)

            # Calculate changed fields for updates
            changed_fields = []
            if action == 'UPDATE' and old_values and new_values:
                changed_fields = [
                    field for field in new_values.keys()
                    if old_values.get(field) != new_values.get(field)
                ]

            # Create audit log entry
            audit_entry = AuditLog(
                table_name=self.__tablename__,
                record_id=self.id,
                action=action,
                old_values=old_values,
                new_values=new_values,
                changed_fields=changed_fields,
                changed_by=user_email or 'system',
                change_reason=reason
            )

            # Add to session but don't commit (let the caller handle commit)
            db.session.add(audit_entry)

        except Exception as e:
            # Log error but don't fail the main operation
            if has_request_context():
                from flask import current_app
                current_app.logger.error(f"Failed to create audit log: {e}")
            print(f"Audit logging error: {e}")  # Fallback logging

    @classmethod
    def find_by_id(cls, id):
        """Find a record by ID"""
        return cls.query.filter_by(id=id).first()

    @classmethod
    def get_all(cls, limit=100, offset=0):
        """Get all records with pagination"""
        return cls.query.offset(offset).limit(limit).all()
