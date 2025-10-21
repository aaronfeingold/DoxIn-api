"""
Payment model
"""
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, String, Date, Text, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from .base import BaseModel


class Payment(BaseModel):
    """Payment tracking model"""
    __tablename__ = 'payments'

    invoice_id = Column(UUID(as_uuid=True), ForeignKey('invoices.id'), nullable=False)

    payment_date = Column(Date, nullable=False)
    amount = Column(DECIMAL(12, 2), nullable=False)
    payment_method = Column(String(50))
    reference_number = Column(String(100))
    notes = Column(Text)

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        if self.payment_date:
            result['payment_date'] = self.payment_date.isoformat()
        result['amount'] = float(self.amount) if self.amount else 0
        return result
