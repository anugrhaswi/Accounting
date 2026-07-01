from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base


def _now():
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(50), nullable=False, default="General")
    description = Column(Text, nullable=True)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    transactions = relationship("Transaction", back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    type = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    reference = Column(String(200), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_now)

    account = relationship("Account", back_populates="transactions")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(10), nullable=False)
    sort_order = Column(Integer, default=0)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=True)
