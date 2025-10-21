"""
User authentication models (Better Auth compatible)
"""
from sqlalchemy import Column, String, Boolean, DateTime
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

    # Application relationships
    uploaded_invoices = relationship(
        "Invoice",
        back_populates="uploaded_by_user",
        foreign_keys="Invoice.uploaded_by_user_id"
    )
    file_storage = relationship("FileStorage", back_populates="user", cascade="all, delete-orphan")
    processing_jobs = relationship("ProcessingJob", back_populates="user", cascade="all, delete-orphan")
    file_access_log = relationship("FileAccessLog", back_populates="user", cascade="all, delete-orphan")

    # Access code relationships
    generated_access_codes = relationship(
        "AccessCode",
        back_populates="generated_by_user",
        foreign_keys="AccessCode.generated_by"
    )
    reviewed_requests = relationship(
        "AccessRequest",
        back_populates="reviewer",
        foreign_keys="AccessRequest.reviewed_by"
    )

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.last_login:
            result['last_login'] = self.last_login.isoformat()
        return result
