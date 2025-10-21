"""
Sales territory model
"""
from sqlalchemy import Column, String, Integer, Boolean
from sqlalchemy.orm import relationship
from .base import BaseModel


class SalesTerritory(BaseModel):
    """Sales territory model"""
    __tablename__ = 'sales_territories'

    territory_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    country_region_code = Column(String(10))
    territory_group = Column(String(100))
    is_active = Column(Boolean, default=True)

    # Relationships
    companies = relationship("Company", back_populates="territory")
    salespersons = relationship("Salesperson", back_populates="territory")
    invoices = relationship("Invoice", back_populates="territory")

    def to_dict(self):
        """Enhanced to_dict with counts"""
        result = super().to_dict()
        result.update({
            'company_count': len(self.companies),
            'salesperson_count': len(self.salespersons),
            'invoice_count': len(self.invoices)
        })
        return result
