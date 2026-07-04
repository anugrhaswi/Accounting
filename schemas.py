"""Dataclass schemas for form data validation.

Each dataclass mirrors a form submission and validates via __post_init__.
Values are parsed from request.form (application/x-www-form-urlencoded).
"""

import math
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AccountCreate:
    """Form data for creating/updating an account."""
    name: str
    type: str = "General"
    description: Optional[str] = None

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("name is required")


@dataclass
class TransactionCreate:
    """Form data for a single transaction (credit/debit/loan/repayment).

    Validates that type is one of the four allowed values and amount > 0.
    """

    account_id: int
    type: str
    amount: float
    category: str = "General"
    description: Optional[str] = None
    reference: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.account_id, int) or self.account_id <= 0:
            raise ValueError("account_id must be a positive integer")
        if self.type not in ("credit", "debit", "loan", "repayment"):
            raise ValueError("type must be 'credit', 'debit', 'loan', or 'repayment'")
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("amount must be a finite positive number")


@dataclass
class TransferCreate:
    """Form data for transferring money between accounts.

    Creates a paired debit (from) and credit (to) with shared reference.
    """

    from_account_id: int
    to_account_id: int
    amount: float
    description: Optional[str] = None

    def __post_init__(self):
        if self.from_account_id == self.to_account_id:
            raise ValueError("from_account_id and to_account_id must be different")
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("amount must be a finite positive number")


@dataclass
class CategoryCreate:
    """Form data for creating a category label."""
    name: str
    type: str

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("name is required")
        if self.type not in ("income", "expense"):
            raise ValueError("type must be 'income' or 'expense'")


@dataclass
class DebtCreate:
    """Form data for creating/updating a debt record.

    due_date is an ISO date string, parsed in the service layer.
    """
    creditor: str
    amount: float
    category: str = "General"
    description: Optional[str] = None
    due_date: Optional[str] = None

    def __post_init__(self):
        if not self.creditor or not self.creditor.strip():
            raise ValueError("creditor is required")
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("amount must be a finite positive number")


@dataclass
class ReceivableCreate:
    """Form data for creating/updating a receivable record.

    due_date is an ISO date string, parsed in the service layer.
    """
    debtor: str
    amount: float
    category: str = "General"
    description: Optional[str] = None
    due_date: Optional[str] = None

    def __post_init__(self):
        if not self.debtor or not self.debtor.strip():
            raise ValueError("debtor is required")
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("amount must be a finite positive number")
