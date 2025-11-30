"""Database models for TabSensei."""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class WatchedProduct(Base):
    """Tracked products for price monitoring."""
    __tablename__ = "watched_products"
    
    id = Column(Integer, primary_key=True)
    product_title = Column(String(500), nullable=False)
    url = Column(String(2000), nullable=False, unique=True)
    current_price = Column(Float, nullable=True)
    currency = Column(String(10), default="USD")
    added_at = Column(DateTime, default=datetime.utcnow)
    last_checked = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    alert_threshold = Column(Float, nullable=True)  # Threshold value (percentage or absolute amount)
    threshold_type = Column(String(20), default="percentage")  # "percentage" or "absolute"
    
    price_history = relationship("PriceHistory", back_populates="product", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="product", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<WatchedProduct(id={self.id}, title={self.product_title[:50]}, price={self.current_price})>"


class PriceHistory(Base):
    """Historical price data for products."""
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("watched_products.id"), nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    recorded_at = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("WatchedProduct", back_populates="price_history")
    
    def __repr__(self) -> str:
        return f"<PriceHistory(id={self.id}, product_id={self.product_id}, price={self.price}, date={self.recorded_at})>"


class TabSession(Base):
    """Store tab browsing sessions."""
    __tablename__ = "tab_sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False, unique=True)
    tabs_data = Column(JSON, nullable=False)  # List of tab info
    categories = Column(JSON, nullable=True)  # Classification results
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<TabSession(id={self.id}, session_id={self.session_id}, tabs={len(self.tabs_data) if self.tabs_data else 0})>"


class UserPreference(Base):
    """Store user preferences and patterns."""
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True)
    key = Column(String(200), nullable=False, unique=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<UserPreference(id={self.id}, key={self.key})>"


class Alert(Base):
    """Price drop alerts for watched products."""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("watched_products.id"), nullable=False)
    alert_type = Column(String(50), default="price_drop")
    message = Column(Text, nullable=False)
    old_price = Column(Float, nullable=True)
    new_price = Column(Float, nullable=True)
    drop_amount = Column(Float, nullable=True)
    drop_percent = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    
    product = relationship("WatchedProduct", back_populates="alerts")
    
    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, product_id={self.product_id}, is_read={self.is_read})>"


