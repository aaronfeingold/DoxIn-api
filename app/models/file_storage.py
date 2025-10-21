"""
File storage models
"""
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from .base import BaseModel


class FileStorage(BaseModel):
    """File storage metadata for Vercel Blob"""
    __tablename__ = 'file_storage'

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    blob_url = Column(Text, nullable=False)
    blob_path = Column(Text, nullable=False)
    file_name = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_hash = Column(String(64))
    upload_source = Column(String(50), default='web')
    is_public = Column(Boolean, default=False)
    access_expires_at = Column(DateTime(timezone=True))
    processing_status = Column(String(50), default='uploaded')
    processing_job_id = Column(UUID(as_uuid=True), ForeignKey('processing_jobs.id'))

    # Relationships
    user = relationship("User", back_populates="file_storage")
    processing_job = relationship("ProcessingJob", foreign_keys=[processing_job_id], back_populates="file_storage")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.access_expires_at:
            result['access_expires_at'] = self.access_expires_at.isoformat()
        result['file_size'] = int(self.file_size) if self.file_size else 0
        return result


class FileAccessLog(BaseModel):
    """File access audit log"""
    __tablename__ = 'file_access_log'

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    file_name = Column(String(500), nullable=False)
    action = Column(String(50), nullable=False)
    ip_address = Column(String(45))  # IPv6 max length
    user_agent = Column(Text)

    # Relationships
    user = relationship("User", back_populates="file_access_log")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        return result
