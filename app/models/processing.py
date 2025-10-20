"""
Document processing models
"""
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Column, String, Integer, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from .base import BaseModel

class DocumentProcessingLog(BaseModel):
    """Document processing log for tracking LLM operations"""
    __tablename__ = 'document_processing_log'

    invoice_id = Column(UUID(as_uuid=True), ForeignKey('invoices.id', ondelete='CASCADE'))

    # Processing details
    processing_step = Column(String(100), nullable=False)
    llm_model = Column(String(100))
    prompt_used = Column(Text)
    raw_response = Column(Text)

    # Results
    extracted_data = Column(JSONB)
    confidence_scores = Column(JSONB)
    validation_errors = Column(JSONB)

    # Performance metrics
    processing_time_ms = Column(Integer)
    tokens_used = Column(Integer)

    processed_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_by = Column(String(255))

    # Relationships
    invoice = relationship("Invoice", back_populates="processing_logs")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.processed_at:
            result['processed_at'] = self.processed_at.isoformat()
        return result
