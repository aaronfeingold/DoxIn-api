"""
Product related models
"""
from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .base import BaseModel


class ProductCategory(BaseModel):
    """Product category model"""
    __tablename__ = 'product_categories'

    category_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)

    # Relationships
    subcategories = relationship("ProductSubCategory", back_populates="category")


class ProductSubCategory(BaseModel):
    """Product subcategory model"""
    __tablename__ = 'product_subcategories'

    subcategory_id = Column(Integer, unique=True, nullable=False)
    category_id = Column(Integer, ForeignKey('product_categories.category_id'), nullable=False)
    name = Column(String(255), nullable=False)

    # Relationships
    category = relationship("ProductCategory", back_populates="subcategories")
    products = relationship("Product", back_populates="subcategory")


class Product(BaseModel):
    """Product model"""
    __tablename__ = 'products'

    # Core identification
    product_id = Column(Integer, unique=True)
    item_number = Column(String(100), unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Product hierarchy
    subcategory_id = Column(Integer, ForeignKey('product_subcategories.subcategory_id'))
    product_model_id = Column(Integer)

    # Physical attributes
    color = Column(String(50))
    size = Column(String(50))
    product_line = Column(String(10))
    class_attr = Column('class', String(10))  # 'class' is reserved keyword
    style = Column(String(10))

    # Financial information
    standard_cost = Column(DECIMAL(12, 2))
    list_price = Column(DECIMAL(12, 2))

    # Manufacturing details
    make_flag = Column(Boolean, default=False)
    finished_goods_flag = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Vector embeddings
    name_embedding = Column(Vector(1536))
    description_embedding = Column(Vector(1536))

    # Relationships
    subcategory = relationship("ProductSubCategory", back_populates="products")
    line_items = relationship("InvoiceLineItem", back_populates="product")

    @property
    def full_description(self):
        """Get full product description including attributes"""
        parts = [self.name]
        if self.color:
            parts.append(f"Color: {self.color}")
        if self.size:
            parts.append(f"Size: {self.size}")
        if self.description and self.description != self.name:
            parts.append(self.description)
        return ' - '.join(parts)

    def to_dict(self):
        """Enhanced to_dict with computed properties"""
        result = super().to_dict()
        # Handle 'class' field name conflict
        result['product_class'] = getattr(self, 'class')
        result['full_description'] = self.full_description
        return result
