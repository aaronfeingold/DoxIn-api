"""
Shipping method model
"""
from sqlalchemy import Column, String, Integer, DECIMAL
from .base import BaseModel


class ShipMethod(BaseModel):
    """Shipping methods"""
    __tablename__ = 'ship_methods'

    method_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    base_rate = Column(DECIMAL(10, 2), default=0)
    rate_per_pound = Column(DECIMAL(10, 2), default=0)

    def to_dict(self):
        """Enhanced to_dict"""
        result = super().to_dict()
        result['base_rate'] = float(self.base_rate) if self.base_rate else 0
        result['rate_per_pound'] = float(self.rate_per_pound) if self.rate_per_pound else 0
        return result
