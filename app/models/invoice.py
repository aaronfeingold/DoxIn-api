"""
Invoice and invoice line item models
"""
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey, Date, DECIMAL
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .base import BaseModel


class Invoice(BaseModel):
    """Invoice/Sales Order model"""
    __tablename__ = 'invoices'

    # Core identification
    sales_order_id = Column(Integer, unique=True, nullable=False)
    invoice_number = Column(String(100), unique=True, nullable=False)
    revision_number = Column(Integer, default=0)

    # Dates
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date)
    ship_date = Column(Date)

    # User who uploaded this invoice - WITH FK CONSTRAINT
    uploaded_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Customer relationships
    customer_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'))
    bill_to_address_id = Column(Integer)
    ship_to_address_id = Column(Integer)

    # Sales assignment
    salesperson_id = Column(UUID(as_uuid=True), ForeignKey('salespersons.id'))
    territory_id = Column(Integer, ForeignKey('sales_territories.territory_id'))

    # Order details
    account_number = Column(String(100))
    po_number = Column(String(100))

    # Shipping details
    ship_method_id = Column(Integer)
    ship_via = Column(String(100))
    fob = Column(String(100))
    carrier_tracking_number = Column(String(100))

    # Payment details
    credit_card_id = Column(Integer)
    credit_card_approval_code = Column(String(100))
    currency_rate_id = Column(Integer)
    terms = Column(String(100))

    # Financial totals
    subtotal = Column(DECIMAL(12, 2), default=0)
    tax_rate = Column(DECIMAL(5, 4), default=0)
    tax_amount = Column(DECIMAL(12, 2), default=0)
    freight = Column(DECIMAL(12, 2), default=0)
    shipping_handling = Column(DECIMAL(12, 2), default=0)
    other_charges = Column(DECIMAL(12, 2), default=0)
    total_amount = Column(DECIMAL(12, 2), nullable=False)

    # Status
    order_status = Column(Integer, default=5)
    payment_status = Column(String(50), default='unpaid')
    online_order_flag = Column(Boolean, default=False)

    # Instructions
    special_instructions = Column(Text)
    notes = Column(Text)

    # Document processing
    original_filename = Column(String(255))
    processed_by_llm = Column(Boolean, default=False)
    confidence_score = Column(DECIMAL(3, 2))
    requires_review = Column(Boolean, default=False)

    # Vector embedding
    content_embedding = Column(Vector(1536))

    # Relationships
    uploaded_by_user = relationship(
        "User",
        back_populates="uploaded_invoices",
        foreign_keys=[uploaded_by_user_id]
    )
    customer = relationship("Company", back_populates="invoices")
    salesperson = relationship("Salesperson", back_populates="invoices")
    territory = relationship("SalesTerritory", back_populates="invoices")
    line_items = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice")
    processing_logs = relationship("DocumentProcessingLog", back_populates="invoice")

    @property
    def calculated_subtotal(self):
        """Calculate subtotal from line items"""
        return sum(item.line_total or 0 for item in self.line_items)

    @property
    def calculated_total(self):
        """Calculate total from components"""
        return (self.subtotal or 0) + (self.tax_amount or 0) + (self.freight or 0) + \
               (self.shipping_handling or 0) + (self.other_charges or 0)

    @property
    def is_totals_valid(self):
        """Check if financial totals are mathematically consistent"""
        subtotal_diff = abs((self.calculated_subtotal or 0) - (self.subtotal or 0))
        total_diff = abs((self.calculated_total or 0) - (self.total_amount or 0))
        return subtotal_diff < 0.01 and total_diff < 0.01

    @property
    def balance_due(self):
        """Calculate remaining balance"""
        total_paid = sum(payment.amount for payment in self.payments)
        return (self.total_amount or 0) - total_paid

    def to_dict(self):
        """Enhanced to_dict with computed properties"""
        result = super().to_dict()
        result.update({
            'calculated_subtotal': float(self.calculated_subtotal or 0),
            'calculated_total': float(self.calculated_total or 0),
            'is_totals_valid': self.is_totals_valid,
            'balance_due': float(self.balance_due or 0),
            'line_item_count': len(self.line_items)
        })
        return result


class InvoiceLineItem(BaseModel):
    """Invoice line item model"""
    __tablename__ = 'invoice_line_items'

    invoice_id = Column(UUID(as_uuid=True), ForeignKey('invoices.id'), nullable=False)
    sales_order_detail_id = Column(Integer, unique=True)
    line_number = Column(Integer, nullable=False)

    # Product reference
    product_id = Column(UUID(as_uuid=True), ForeignKey('products.id'))

    # Item details
    item_number = Column(String(100))
    description = Column(Text, nullable=False)

    # Quantities and pricing
    quantity = Column(Integer, nullable=False)
    unit_price = Column(DECIMAL(12, 2), nullable=False)
    unit_price_discount = Column(DECIMAL(5, 2), default=0)
    line_total = Column(DECIMAL(12, 2), nullable=False)

    # Special offers
    special_offer_id = Column(Integer)

    # Shipping
    carrier_tracking_number = Column(String(100))

    # Metadata
    unit_of_measure = Column(String(50))

    # Vector embedding
    description_embedding = Column(Vector(1536))

    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")
    product = relationship("Product", back_populates="line_items")

    @property
    def calculated_line_total(self):
        """Calculate line total from quantity and unit price with discount"""
        base_total = (self.quantity or 0) * (self.unit_price or 0)
        discount_amount = base_total * (self.unit_price_discount or 0)
        return base_total - discount_amount

    @property
    def is_line_total_valid(self):
        """Check if line total calculation is correct"""
        diff = abs((self.calculated_line_total or 0) - (self.line_total or 0))
        return diff < 0.01

    def to_dict(self):
        """Enhanced to_dict with computed properties"""
        result = super().to_dict()
        result.update({
            'calculated_line_total': float(self.calculated_line_total or 0),
            'is_line_total_valid': self.is_line_total_valid
        })
        return result
