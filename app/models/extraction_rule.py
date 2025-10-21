"""
Extraction rules model
"""
from sqlalchemy import Column, String, Boolean, Text, Integer, DECIMAL
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from .base import BaseModel


class ExtractionRule(BaseModel):
    """LLM extraction rules"""
    __tablename__ = 'extraction_rules'

    rule_name = Column(String(255), nullable=False)
    rule_type = Column(String(100), nullable=False)
    pattern_regex = Column(Text)
    extraction_prompt = Column(Text)
    validation_criteria = Column(JSONB)
    confidence_threshold = Column(DECIMAL(3, 2), default=0.80)
    document_types = Column(ARRAY(Text))
    vendor_patterns = Column(ARRAY(Text))
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=100)

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.confidence_threshold:
            result['confidence_threshold'] = float(self.confidence_threshold)
        return result
