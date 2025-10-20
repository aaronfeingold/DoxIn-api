"""
Account model for Better Auth authentication providers
"""
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class Account(BaseModel):
    """Account model for authentication providers (matches Better Auth schema)"""
    __tablename__ = 'account'

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    account_id = Column(String, nullable=False)
    provider_id = Column(String, nullable=False)
    access_token = Column(Text)
    refresh_token = Column(Text)
    id_token = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    password = Column(String(255))  # Bcrypt hashed password for credential provider

    # Relationships
    user = relationship("User", back_populates="accounts")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.expires_at:
            result['expires_at'] = self.expires_at.isoformat()
        # Don't include password in dict for security
        result.pop('password', None)
        return result
