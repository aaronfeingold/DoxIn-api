"""
Audit log model
"""
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy import Column, String, Text, DateTime, func
from .base import BaseModel

class AuditLog(BaseModel):
    """Audit trail"""
    __tablename__ = 'audit_log'

    table_name = Column(String(100), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(50), nullable=False)
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    changed_fields = Column(ARRAY(Text))
    changed_by = Column(String(255))
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    change_reason = Column(Text)

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.changed_at:
            result['changed_at'] = self.changed_at.isoformat()
        return result
