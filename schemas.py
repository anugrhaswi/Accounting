from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AccountCreate:
    name: str
    type: str = "General"
    description: Optional[str] = None


@dataclass
class TransactionCreate:
    account_id: int
    type: str
    amount: float
    category: str = "General"
    description: Optional[str] = None
    reference: Optional[str] = None

    def __post_init__(self):
        if self.type not in ("credit", "debit"):
            raise ValueError("type must be 'credit' or 'debit'")
        if self.amount <= 0:
            raise ValueError("amount must be > 0")


@dataclass
class TransferCreate:
    from_account_id: int
    to_account_id: int
    amount: float
    description: Optional[str] = None

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("amount must be > 0")


@dataclass
class CategoryCreate:
    name: str
    type: str

    def __post_init__(self):
        if self.type not in ("income", "expense"):
            raise ValueError("type must be 'income' or 'expense'")


@dataclass
class DebtCreate:
    creditor: str
    amount: float
    category: str = "General"
    description: Optional[str] = None
    due_date: Optional[str] = None

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("amount must be > 0")
