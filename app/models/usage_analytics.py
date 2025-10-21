"""
Usage analytics models for tracking user behavior
"""
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from .base import BaseModel


class UsageAnalytics(BaseModel):
    """Usage tracking for pages and features"""
    __tablename__ = 'usage_analytics'

    # User identification
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    session_id = Column(String(255))

    # Page information
    route = Column(String(500), nullable=False)  # /admin/reports, /invoices, etc.
    page_title = Column(String(255))
    referrer = Column(String(500))

    # Timing
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    duration_seconds = Column(Integer)  # Time spent on page

    # Context
    action = Column(String(100))  # page_view, button_click, form_submit, etc.
    context_metadata = Column('metadata', JSONB)  # Additional context

    # Device/browser info
    user_agent = Column(String(500))
    ip_address = Column(String(50))

    # Relationships
    user = relationship("User", backref="analytics")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.viewed_at:
            result['viewed_at'] = self.viewed_at.isoformat()
        return result


class PageViewSummary(BaseModel):
    """Aggregated page view statistics (materialized for performance)"""
    __tablename__ = 'page_view_summary'

    date = Column(DateTime(timezone=True), nullable=False)
    route = Column(String(500), nullable=False)

    # Aggregates
    unique_users = Column(Integer, default=0)
    total_views = Column(Integer, default=0)
    avg_duration_seconds = Column(Integer, default=0)

    # Context
    context_metadata = Column('metadata', JSONB)

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.date:
            result['date'] = self.date.isoformat()
        return result
