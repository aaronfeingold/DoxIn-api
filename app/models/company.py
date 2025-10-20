"""
Company and address models
"""
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .base import BaseModel

class Company(BaseModel):
    """Company model for both individual and business customers"""
    __tablename__ = 'companies'

    # Core identification
    customer_id = Column(Integer, unique=True)
    business_entity_id = Column(Integer)
    account_number = Column(String(100))

    # Company/Individual details
    company_type = Column(String(50), default='individual')  # 'individual', 'business'
    company_name = Column(String(255))
    first_name = Column(String(100))
    middle_name = Column(String(100))
    last_name = Column(String(100))

    # Primary address
    address_type = Column(String(50), default='billing')
    street_address = Column(Text)
    address_line2 = Column(Text)
    city = Column(String(100))
    state_province = Column(String(100))
    postal_code = Column(String(20))
    country_region = Column(String(100), default='United States')

    # Contact information
    phone = Column(String(50))
    fax = Column(String(50))
    email = Column(String(255))
    website = Column(String(255))

    # Business details
    tax_id = Column(String(50))
    territory_id = Column(Integer, ForeignKey('sales_territories.territory_id'))

    # Status
    is_active = Column(Boolean, default=True)

    # Vector embeddings
    name_embedding = Column(Vector(1536))
    address_embedding = Column(Vector(1536))

    # Relationships
    territory = relationship("SalesTerritory", back_populates="companies")
    additional_addresses = relationship("CompanyAddress", back_populates="company", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="customer")

    @property
    def full_name(self):
        """Get full name for individuals or company name for businesses"""
        if self.company_type == 'business':
            return self.company_name
        else:
            parts = [self.first_name, self.middle_name, self.last_name]
            return ' '.join(filter(None, parts))

    @property
    def display_name(self):
        """Get the best display name for this company/person"""
        return self.company_name or self.full_name

    @property
    def full_address(self):
        """Get formatted full address"""
        parts = []
        if self.street_address:
            parts.append(self.street_address)
        if self.address_line2:
            parts.append(self.address_line2)

        city_state_zip = []
        if self.city:
            city_state_zip.append(self.city)
        if self.state_province:
            city_state_zip.append(self.state_province)
        if self.postal_code:
            city_state_zip.append(self.postal_code)

        if city_state_zip:
            parts.append(', '.join(city_state_zip))

        if self.country_region and self.country_region != 'United States':
            parts.append(self.country_region)

        return '\n'.join(parts)

    def to_dict(self):
        """Enhanced to_dict with computed properties"""
        result = super().to_dict()
        result.update({
            'full_name': self.full_name,
            'display_name': self.display_name,
            'full_address': self.full_address
        })
        return result


class CompanyAddress(BaseModel):
    """Additional addresses for companies"""
    __tablename__ = 'company_addresses'

    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False)
    address_type = Column(String(50), nullable=False)
    street_address = Column(Text, nullable=False)
    address_line2 = Column(Text)
    city = Column(String(100))
    state_province = Column(String(100))
    postal_code = Column(String(20))
    country_region = Column(String(100), default='United States')

    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Vector embedding
    full_address_embedding = Column(Vector(1536))

    # Relationships
    company = relationship("Company", back_populates="additional_addresses")

    @property
    def full_address(self):
        """Get formatted full address"""
        parts = []
        if self.street_address:
            parts.append(self.street_address)
        if self.address_line2:
            parts.append(self.address_line2)

        city_state_zip = []
        if self.city:
            city_state_zip.append(self.city)
        if self.state_province:
            city_state_zip.append(self.state_province)
        if self.postal_code:
            city_state_zip.append(self.postal_code)

        if city_state_zip:
            parts.append(', '.join(city_state_zip))

        if self.country_region and self.country_region != 'United States':
            parts.append(self.country_region)

        return '\n'.join(parts)