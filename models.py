"""
SQLAlchemy ORM models for the monitoring bot.
All models use integer timestamps (Unix epoch) for consistency.
"""
from sqlalchemy.orm import declarative_base, relationship # type: ignore
import sqlalchemy 
from sqlalchemy import Column, Integer, String, Boolean, Text, Float, ForeignKey # type: ignore
from sqlalchemy.orm import declarative_base, relationship # type: ignore
from typing import Optional

Base = declarative_base()


class Subscription(Base):
    """
    Tracks which chat_ids are authorized to use the bot.
    Admin must explicitly add subscriptions - no auto-subscribe.
    """
    __tablename__ = "subscriptions"
    
    chat_id = Column(Integer, primary_key=True)
    created_at = Column(Integer)
    
    def __repr__(self) -> str:
        return f"<Subscription(chat_id={self.chat_id})>"


class Customer(Base):
    """
    Customer configuration per chat_id.
    One customer can have multiple targets to monitor.
    """
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, nullable=False, index=True)
    alerts_enabled = Column(Boolean, default=True)
    interval_seconds = Column(Integer, default=60)
    failure_threshold = Column(Integer, default=3)
    escalation_threshold = Column(Integer, default=5)
    created_at = Column(Integer)
    updated_at = Column(Integer)
    
    # Cascade delete: when customer is deleted, all their targets are deleted
    targets = relationship("Target", cascade="all, delete-orphan", back_populates="customer")
    
    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, chat_id={self.chat_id})>"


class Target(Base):
    """
    Individual monitoring target (IP:port) owned by a customer.
    """
    __tablename__ = "targets"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True, index=True)
    last_checked = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    
    customer = relationship("Customer", back_populates="targets")
    
    def __repr__(self) -> str:
        return f"<Target(id={self.id}, name={self.name}, {self.ip}:{self.port})>"


class History(Base):
    """
    Historical check results for monitoring and analytics.
    """
    __tablename__ = "history"
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(Integer, index=True)
    customer_chat_id = Column(Integer, index=True)
    target_name = Column(String)
    status = Column(String)  # 'success' or 'failure'
    error = Column(Text)
    response_time = Column(Float)
    
    def __repr__(self) -> str:
        return f"<History(id={self.id}, target={self.target_name}, status={self.status})>"


class AuditLog(Base):
    """
    Audit trail for all administrative actions and config changes.
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    actor_chat_id = Column(Integer, index=True)
    action = Column(String)
    details = Column(Text)
    created_at = Column(Integer)
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, actor={self.actor_chat_id}, action={self.action})>"