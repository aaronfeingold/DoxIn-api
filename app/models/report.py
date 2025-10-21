"""
Report models for admin analytics and custom reports
"""
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Integer
from sqlalchemy.orm import relationship
from .base import BaseModel


class Report(BaseModel):
    """Generated report model"""
    __tablename__ = 'reports'

    # Ownership
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Report details
    title = Column(String(255), nullable=False)
    description = Column(Text)
    report_type = Column(String(100), nullable=False)  # financial, sales, custom, etc.

    # Status
    status = Column(String(50), default='pending')  # pending, processing, completed, failed
    progress = Column(Integer, default=0)  # 0-100

    # Configuration
    parameters = Column(JSONB)  # Report filters, date ranges, etc.
    template_id = Column(UUID(as_uuid=True), ForeignKey('saved_report_templates.id'))

    # Results
    file_path = Column(String(500))  # Path to generated file (PDF/PNG/Excel)
    file_format = Column(String(20))  # pdf, png, xlsx, csv
    file_size = Column(Integer)  # bytes
    preview_url = Column(String(500))  # URL for quick preview

    # Metadata
    error_message = Column(Text)
    processing_time_seconds = Column(Integer)
    generated_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))  # Auto-delete old reports

    # Relationships
    user = relationship("User", backref="reports")
    template = relationship("SavedReportTemplate", backref="reports")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.generated_at:
            result['generated_at'] = self.generated_at.isoformat()
        if self.expires_at:
            result['expires_at'] = self.expires_at.isoformat()
        return result


class SavedReportTemplate(BaseModel):
    """User-defined report templates for reuse"""
    __tablename__ = 'saved_report_templates'

    # Ownership
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Template details
    name = Column(String(255), nullable=False)
    description = Column(Text)
    report_type = Column(String(100), nullable=False)

    # Configuration
    parameters = Column(JSONB, nullable=False)  # Saved filters, chart types, etc.
    is_public = Column(String(20), default='private')  # private, team, public

    # Usage stats
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", backref="report_templates")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.last_used_at:
            result['last_used_at'] = self.last_used_at.isoformat()
        return result
