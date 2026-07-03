"""SQLAlchemy ORM models for the accounting application.

Tables:
  accounts       — user-managed ledgers (bank, wallet, cash)
  transactions   — individual credit/debit/loan/repayment entries
  categories     — income/expense category labels
  debts          — money borrowed (liability tracking)
  receivables    — money lent out (asset tracking)
  daily_profit_log — daily P&L snapshot
  settings       — key-value config store (fixed_capital, etc.)
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base


def _now():
    """Return current UTC datetime for default column values."""
    return datetime.now(timezone.utc)


class Account(Base):
    """A financial account (bank, wallet, cash, etc.).

    Balance is updated automatically when transactions are created/deleted.
    """

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
    """A single financial transaction linked to an account.

    Four types: credit (income), debit (expense), loan (money borrowed),
    repayment (money returned). Reference field links to debt/receivable/transfer pairs.
    """

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
    """Income or expense label used to group transactions."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(10), nullable=False)
    sort_order = Column(Integer, default=0)


class Debt(Base):
    """Money borrowed from a creditor (liability).

    Lifecycle: created (unpaid) → loan received → settled (paid).
    received_at tracks when the loan was deposited into an account.
    settled_at tracks when the debt was repaid.
    """

    __tablename__ = "debts"

    id = Column(Integer, primary_key=True, index=True)
    creditor = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(10), nullable=False, default="unpaid")
    created_at = Column(DateTime(timezone=True), default=_now)
    received_at = Column(DateTime(timezone=True), nullable=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)


class Receivable(Base):
    """Money lent to a debtor (asset).

    Lifecycle: created (unreceived) → payment received (received).
    """

    __tablename__ = "receivables"

    id = Column(Integer, primary_key=True, index=True)
    debtor = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(10), nullable=False, default="unreceived")
    created_at = Column(DateTime(timezone=True), default=_now)
    received_at = Column(DateTime(timezone=True), nullable=True)


class DailyProfitLog(Base):
    """Daily profit and loss snapshot.

    profit = income - expenses. Receivable and capital changes are stored
    as informational columns. Only dates with activity get an entry.
    """

    __tablename__ = "daily_profit_log"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True)
    income = Column(Float, nullable=False, default=0.0)
    expenses = Column(Float, nullable=False, default=0.0)
    new_receivables = Column(Float, nullable=False, default=0.0)
    received_receivables = Column(Float, nullable=False, default=0.0)
    capital = Column(Float, nullable=False, default=0.0)
    capital_delta = Column(Float, nullable=False, default=0.0)
    profit = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class Setting(Base):
    """Key-value store for application settings (e.g. fixed_capital)."""

    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=True)
