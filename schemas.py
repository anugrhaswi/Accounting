from pydantic import BaseModel, Field
from typing import Optional


class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(default="General", max_length=50)
    description: Optional[str] = None


class TransactionCreate(BaseModel):
    account_id: int
    type: str = Field(..., pattern="^(credit|debit)$")
    amount: float = Field(..., gt=0)
    category: str = Field(default="General", max_length=50)
    description: Optional[str] = None
    reference: Optional[str] = None


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: float = Field(..., gt=0)
    description: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(income|expense)$")
