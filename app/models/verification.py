"""
Verification model for Better Auth magic links and email verification
"""
from sqlalchemy import Column, String, DateTime, UniqueConstraint
from .base import BaseModel


class Verification(BaseModel):
    """Verification model for magic links and email verification (matches Better Auth schema)"""
    __tablename__ = 'verification'

    identifier = Column(String, nullable=False)
    value = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint('identifier', 'value', name='verification_identifier_value_key'),
    )

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.expires_at:
            result['expires_at'] = self.expires_at.isoformat()
        return result

    def is_valid(self):
        """Check if verification is still valid"""
        from datetime import datetime
        return datetime.utcnow() < self.expires_at.replace(tzinfo=None)
