"""
User authentication models (Better Auth compatible)
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import BaseModel


class User(BaseModel):
    """User model for authentication (matches Better Auth schema)"""
    __tablename__ = 'users'

    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    email_verified = Column(Boolean, default=False)
    image = Column(String)
    access_code = Column(String(50), unique=True)  # Custom field for invitation system
    role = Column(String(50), default='user')
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))

    # Relationships (Better Auth tables)
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    # Application relationships
    file_storage = relationship("FileStorage", back_populates="user", cascade="all, delete-orphan")
    processing_jobs = relationship("ProcessingJob", back_populates="user", cascade="all, delete-orphan")
    file_access_log = relationship("FileAccessLog", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.last_login:
            result['last_login'] = self.last_login.isoformat()
        return result


class Session(BaseModel):
    """Session model for Better Auth session management"""
    __tablename__ = 'session'

    # Override id to use String instead of UUID for Better Auth tokens
    id = Column(String, primary_key=True)

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    token = Column(String, unique=True, nullable=False)
    ip_address = Column(String)
    user_agent = Column(String)

    # Relationships
    user = relationship("User", back_populates="sessions")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.expires_at:
            result['expires_at'] = self.expires_at.isoformat()
        return result

    def is_valid(self):
        """Check if session is still valid"""
        from datetime import datetime
        return datetime.utcnow() < self.expires_at.replace(tzinfo=None)
