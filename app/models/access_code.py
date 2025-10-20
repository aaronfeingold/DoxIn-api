"""
Access code model for user invitations
"""
from sqlalchemy import Column, String, DateTime, Boolean
from datetime import datetime, timedelta
from .base import BaseModel


class AccessCode(BaseModel):
    """Access code model for user invitation system"""
    __tablename__ = 'access_codes'

    code = Column(String(12), unique=True, nullable=False, index=True)
    is_used = Column(Boolean, default=False)
    used_by_email = Column(String(255))
    used_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.used_at:
            result['used_at'] = self.used_at.isoformat()
        if self.expires_at:
            result['expires_at'] = self.expires_at.isoformat()
        return result

    def is_valid(self):
        """Check if access code is still valid"""
        if self.is_used:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True

    def mark_as_used(self, email):
        """Mark access code as used"""
        self.is_used = True
        self.used_by_email = email
        self.used_at = datetime.utcnow()
