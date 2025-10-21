"""
Access request model for user-initiated access requests
"""
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class AccessRequest(BaseModel):
    """User-initiated access request model"""
    __tablename__ = 'access_requests'

    email = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    message = Column(Text)
    status = Column(String(50), default='pending', nullable=False)  # pending, approved, rejected
    requested_at = Column(DateTime(timezone=True), nullable=False)
    reviewed_at = Column(DateTime(timezone=True))
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    rejection_reason = Column(Text)

    # Relationships
    reviewer = relationship("User", back_populates="reviewed_requests", foreign_keys=[reviewed_by])
    access_code = relationship("AccessCode", back_populates="access_request", uselist=False)

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.requested_at:
            result['requested_at'] = self.requested_at.isoformat()
        if self.reviewed_at:
            result['reviewed_at'] = self.reviewed_at.isoformat()
        return result

    def approve(self, reviewer_user_id):
        """Mark request as approved"""
        from datetime import datetime
        self.status = 'approved'
        self.reviewed_by = reviewer_user_id
        self.reviewed_at = datetime.utcnow()

    def reject(self, reviewer_user_id, reason=None):
        """Mark request as rejected"""
        from datetime import datetime
        self.status = 'rejected'
        self.reviewed_by = reviewer_user_id
        self.reviewed_at = datetime.utcnow()
        self.rejection_reason = reason
