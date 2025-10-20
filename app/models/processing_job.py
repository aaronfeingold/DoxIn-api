"""
Processing job models
"""
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer, DECIMAL
from sqlalchemy.orm import relationship
from .base import BaseModel

class ProcessingJob(BaseModel):
    """Processing jobs for async file processing"""
    __tablename__ = 'processing_jobs'

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    file_storage_id = Column(UUID(as_uuid=True), ForeignKey('file_storage.id'))
    job_type = Column(String(100), nullable=False)
    auto_save = Column(Boolean, default=True)
    cleanup = Column(Boolean, default=True)
    status = Column(String(50), default='pending')
    progress = Column(Integer, default=0)
    current_stage = Column(String(100))
    error_message = Column(Text)
    result_data = Column(JSONB)
    confidence_score = Column(DECIMAL(3, 2))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    estimated_completion = Column(DateTime(timezone=True))
    viewed_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="processing_jobs")
    file_storage = relationship("FileStorage", foreign_keys="FileStorage.processing_job_id", back_populates="processing_job")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.started_at:
            result['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            result['completed_at'] = self.completed_at.isoformat()
        if self.estimated_completion:
            result['estimated_completion'] = self.estimated_completion.isoformat()
        if self.viewed_at:
            result['viewed_at'] = self.viewed_at.isoformat()
        if self.confidence_score:
            result['confidence_score'] = float(self.confidence_score)
        return result

    def update_metrics(self):
        """Update Prometheus metrics for this job"""
        try:
            from app.services.metrics_service import MetricsService

            # Track job completion if status changed to completed/failed
            if self.status in ['completed', 'failed']:
                MetricsService.track_invoice_processing(self.status)

            # Track processing duration if completed
            if self.status == 'completed' and self.started_at and self.completed_at:
                duration = (self.completed_at - self.started_at).total_seconds()
                MetricsService.track_processing_job_duration(self.job_type, duration)

            # Track extraction accuracy if available
            if self.confidence_score and self.status == 'completed':
                MetricsService.track_extraction_accuracy(self.job_type, float(self.confidence_score))

        except ImportError:
            # Metrics service not available, skip
            pass
        except Exception:
            # Don't break the application if metrics fail
            pass

    @classmethod
    def update_active_job_metrics(cls):
        """Update active job count metrics"""
        try:
            from app.services.metrics_service import MetricsService
            from app import db
            from sqlalchemy import func

            # Get job counts by type and status
            job_counts = db.session.query(
                cls.job_type,
                cls.status,
                func.count(cls.id)
            ).group_by(cls.job_type, cls.status).all()

            # Reset all metrics first (to handle deleted jobs)
            job_types = db.session.query(cls.job_type).distinct().all()
            statuses = ['pending', 'processing', 'completed', 'failed']

            for job_type_row in job_types:
                for status in statuses:
                    MetricsService.update_active_jobs(job_type_row[0], status, 0)

            # Update with actual counts
            for job_type, status, count in job_counts:
                MetricsService.update_active_jobs(job_type, status, count)

        except ImportError:
            # Metrics service not available, skip
            pass
        except Exception:
            # Don't break the application if metrics fail
            pass
