"""
Salesperson model
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .base import BaseModel


class Salesperson(BaseModel):
    """Salesperson model"""
    __tablename__ = 'salespersons'

    salesperson_id = Column(Integer, unique=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True)
    phone = Column(String(50))
    employee_id = Column(String(50), unique=True)
    department = Column(String(100))
    territory_id = Column(Integer, ForeignKey('sales_territories.territory_id'))
    is_active = Column(Boolean, default=True)

    # Vector embedding
    name_embedding = Column(Vector(1536))

    # Relationships
    territory = relationship("SalesTerritory", back_populates="salespersons")
    invoices = relationship("Invoice", back_populates="salesperson")

    def to_dict(self):
        """Enhanced to_dict with counts"""
        result = super().to_dict()
        result['invoice_count'] = len(self.invoices)
        return result
