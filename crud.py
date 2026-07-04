"""Database CRUD operations for all models.

Each function takes a SQLAlchemy Session as the first parameter and
raises ValueError for business-rule violations.
"""

import uuid
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import models
import schemas
from schemas import asdict


def get_accounts(db: Session):
    """Return all accounts sorted by name."""
    result = db.execute(select(models.Account).order_by(models.Account.name))
    return result.scalars().all()


def get_account(db: Session, account_id: int):
    """Return a single account by ID. Raises ValueError if not found."""
    account = db.get(models.Account, account_id)
    if not account:
        raise ValueError("Account not found")
    return account


def create_account(db: Session, data: schemas.AccountCreate):
    """Create a new account from form data."""
    account = models.Account(**asdict(data))
    db.add(account)
    db.flush()
    db.refresh(account)
    return account


def delete_account(db: Session, account_id: int):
    """Delete an account if it has no transactions. Raises ValueError otherwise."""
    account = get_account(db, account_id)
    result = db.execute(
        select(models.Transaction).where(models.Transaction.account_id == account_id).limit(1)
    )
    if result.first():
        raise ValueError("Cannot delete account with existing transactions")
    db.delete(account)
    db.flush()


def get_total_balance(db: Session):
    """Return the sum of all account balances."""
    result = db.execute(select(func.coalesce(func.sum(models.Account.balance), 0)))
    return result.scalar()


def get_setting(db: Session, key: str, default: str = None):
    """Read a setting from the key-value store. Returns default if missing."""
    result = db.execute(
        select(models.Setting).where(models.Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting and setting.value is not None else default


def set_setting(db: Session, key: str, value: str):
    """Write a setting to the key-value store (insert or update)."""
    result = db.execute(
        select(models.Setting).where(models.Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(models.Setting(key=key, value=value))
    db.flush()


def get_transactions(db: Session, account_id: int = None, txn_type: str = None, skip: int = 0, limit: int = 100):
    """Return transactions with optional filters, newest first.

    Eager-loads the related account. Filters by account_id and/or type.
    """
    query = (
        select(models.Transaction)
        .options(selectinload(models.Transaction.account))
        .order_by(models.Transaction.timestamp.desc())
    )
    if account_id:
        query = query.where(models.Transaction.account_id == account_id)
    if txn_type:
        query = query.where(models.Transaction.type == txn_type)
    result = db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


def create_transaction(db: Session, data: schemas.TransactionCreate):
    """Create a transaction and update the account balance.

    Validates: no direct Transfer category, no reserved reference prefix,
    sufficient balance for debit/repayment. Raises ValueError on failure.
    """
    if data.category == "Transfer":
        raise ValueError("Cannot create a transaction with category 'Transfer' directly. Use the transfer form.")
    if data.reference:
        if data.reference.startswith("debt:") or data.reference.startswith("receivable:") or data.reference.startswith("xfer:"):
            raise ValueError("Reference prefix not allowed")
    account = get_account(db, data.account_id)
    if data.type in ("debit", "repayment") and account.balance < data.amount:
        raise ValueError("Insufficient balance")
    transaction = models.Transaction(**asdict(data))
    if data.type in ("credit", "loan"):
        account.balance += data.amount
    else:
        account.balance -= data.amount
    db.add(transaction)
    db.flush()
    db.refresh(transaction)
    return transaction


def get_transaction(db: Session, transaction_id: int):
    """Return a single transaction by ID. Raises ValueError if not found."""
    txn = db.get(models.Transaction, transaction_id)
    if not txn:
        raise ValueError("Transaction not found")
    return txn


def delete_transaction(db: Session, transaction_id: int):
    """Delete a transaction and reverse its balance change.

    For transfers: also reverses the paired transaction.
    For debt-linked txns: reverts debt status/received_at as needed.
    For receivable-linked txns: reverts receivable status.
    """
    txn = get_transaction(db, transaction_id)
    account = txn.account

    if txn.category == "Transfer" and txn.reference and txn.reference.startswith("xfer:"):
        # Find and reverse the paired side of the transfer
        pair_type = "credit" if txn.type == "debit" else "debit"
        pair_txn = db.execute(
            select(models.Transaction).where(
                models.Transaction.reference == txn.reference,
                models.Transaction.type == pair_type,
                models.Transaction.id != txn.id,
            ).limit(1)
        ).scalar_one_or_none()

        if pair_txn:
            pair_account = pair_txn.account
            if pair_txn.type == "credit":
                if pair_account.balance < pair_txn.amount:
                    raise ValueError("Cannot undo: pair account has insufficient balance")
                pair_account.balance -= pair_txn.amount
            else:
                pair_account.balance += pair_txn.amount
            db.delete(pair_txn)

        if txn.type in ("debit", "repayment"):
            account.balance += txn.amount
        else:
            if account.balance < txn.amount:
                raise ValueError("Cannot undo: insufficient balance to reverse credit")
            account.balance -= txn.amount

        db.delete(txn)
        db.flush()
        return

    # Reverse the balance change
    if txn.type in ("credit", "loan"):
        if account.balance < txn.amount:
            raise ValueError("Cannot undo: insufficient balance to reverse credit")
        account.balance -= txn.amount
    else:
        account.balance += txn.amount

    # Revert linked debt state if this was a debt transaction
    if txn.reference and txn.reference.startswith("debt:"):
        try:
            debt_id = int(txn.reference.split(":", 1)[1])
            debt = db.get(models.Debt, debt_id)
            if debt:
                if txn.type == "loan":
                    # Block deleting a loan if the debt has already been repaid
                    if debt.status == "paid":
                        raise ValueError("Cannot delete loan transaction: debt is paid. Delete the repayment first.")
                    debt.received_at = None
                elif txn.type == "repayment" and debt.status == "paid":
                    debt.status = "unpaid"
                    debt.settled_at = None
        except (ValueError, TypeError):
            pass

    # Revert linked receivable state if this was a receivable transaction
    if txn.reference and txn.reference.startswith("receivable:"):
        try:
            recv_id = int(txn.reference.split(":", 1)[1])
            recv = db.get(models.Receivable, recv_id)
            if recv and recv.status == "received":
                recv.status = "unreceived"
                recv.received_at = None
        except (ValueError, TypeError):
            pass

    db.delete(txn)
    db.flush()


def transfer_money(db: Session, data: schemas.TransferCreate):
    """Transfer money between two accounts.

    Creates a paired debit (from) and credit (to) transaction sharing
    a generated xfer: reference. Both are created in a single flush.
    """
    if data.from_account_id == data.to_account_id:
        raise ValueError("Cannot transfer to the same account")

    from_account = get_account(db, data.from_account_id)
    to_account = get_account(db, data.to_account_id)

    if from_account.balance < data.amount:
        raise ValueError("Insufficient balance")

    transfer_ref = f"xfer:{uuid.uuid4().hex[:12]}"

    debit_txn = models.Transaction(
        account_id=data.from_account_id,
        type="debit",
        amount=data.amount,
        category="Transfer",
        description=data.description or f"Transfer to {to_account.name}",
        reference=transfer_ref,
    )
    from_account.balance -= data.amount

    credit_txn = models.Transaction(
        account_id=data.to_account_id,
        type="credit",
        amount=data.amount,
        category="Transfer",
        description=data.description or f"Transfer from {from_account.name}",
        reference=transfer_ref,
    )
    to_account.balance += data.amount

    db.add(debit_txn)
    db.add(credit_txn)
    db.flush()
    db.refresh(debit_txn)
    db.refresh(credit_txn)
    return debit_txn, credit_txn


def get_categories(db: Session, cat_type: str = None):
    """Return categories, optionally filtered by income/expense type, sorted by sort_order then name."""
    query = select(models.Category).order_by(models.Category.sort_order, models.Category.name)
    if cat_type:
        query = query.where(models.Category.type == cat_type)
    result = db.execute(query)
    return result.scalars().all()


def create_category(db: Session, data: schemas.CategoryCreate):
    """Create a new category label."""
    category = models.Category(**asdict(data))
    db.add(category)
    db.flush()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: int):
    """Delete a category if no transactions use it. Raises ValueError otherwise."""
    category = db.get(models.Category, category_id)
    if not category:
        raise ValueError("Category not found")
    result = db.execute(
        select(models.Transaction).where(models.Transaction.category == category.name).limit(1)
    )
    if result.first():
        raise ValueError("Cannot delete category with existing transactions")
    db.delete(category)
    db.flush()


"""Default category seeds for fresh installations."""
DEFAULT_CATEGORIES = [
    {"name": "Aadhaar", "type": "income", "sort_order": 1},
    {"name": "Recharge", "type": "income", "sort_order": 2},
    {"name": "Bill Payment", "type": "income", "sort_order": 3},
    {"name": "Insurance", "type": "income", "sort_order": 4},
    {"name": "IRCTC", "type": "income", "sort_order": 5},
    {"name": "Other Income", "type": "income", "sort_order": 99},
    {"name": "Rent", "type": "expense", "sort_order": 1},
    {"name": "Electricity", "type": "expense", "sort_order": 2},
    {"name": "Internet", "type": "expense", "sort_order": 3},
    {"name": "Supplies", "type": "expense", "sort_order": 4},
    {"name": "Food", "type": "expense", "sort_order": 5},
    {"name": "Other Expense", "type": "expense", "sort_order": 99},
]


def seed_default_categories(db: Session):
    """Seed 12 default categories if the categories table is empty.

    Income: Aadhaar, Recharge, Bill Payment, Insurance, IRCTC, Other Income.
    Expense: Rent, Electricity, Internet, Supplies, Food, Other Expense.
    """
    result = db.execute(select(models.Category).limit(1))
    if result.first():
        return
    for cat in DEFAULT_CATEGORIES:
        db.add(models.Category(**cat))
    db.flush()


def get_daily_summary(db: Session, date: datetime = None):
    """Return today's income, expenses, profit, and per-category breakdown.

    Excludes Transfer transactions. Uses credit for income and debit for expenses.
    """
    if date is None:
        date = datetime.now(timezone.utc)
    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    income = db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type.in_(["credit"]))
        .where(models.Transaction.category != "Transfer")
    )
    total_income = income.scalar()

    expenses = db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type.in_(["debit"]))
        .where(models.Transaction.category != "Transfer")
    )
    total_expenses = expenses.scalar()

    income_by_cat = db.execute(
        select(models.Transaction.category, func.sum(models.Transaction.amount))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type.in_(["credit"]))
        .where(models.Transaction.category != "Transfer")
        .group_by(models.Transaction.category)
    )

    expense_by_cat = db.execute(
        select(models.Transaction.category, func.sum(models.Transaction.amount))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type.in_(["debit"]))
        .where(models.Transaction.category != "Transfer")
        .group_by(models.Transaction.category)
    )

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "profit": total_income - total_expenses,
        "income_by_category": {r[0] or "General": r[1] for r in income_by_cat},
        "expense_by_category": {r[0] or "General": r[1] for r in expense_by_cat},
    }


def log_daily_profit(db: Session, log_date: date, profit: float):
    """Create or update a daily profit log entry with a manually entered profit value."""
    entry = db.execute(
        select(models.DailyProfitLog).where(models.DailyProfitLog.date == log_date)
    ).scalar_one_or_none()
    if entry:
        entry.profit = profit
        entry.updated_at = datetime.now(timezone.utc)
    else:
        entry = models.DailyProfitLog(
            date=log_date, profit=profit,
            income=0, expenses=0,
            new_receivables=0, received_receivables=0,
            capital=0, capital_delta=0,
        )
        db.add(entry)
    db.flush()
    return entry


def get_daily_profit_logs(db: Session, limit: int = 365):
    """Return the most recent daily profit log entries."""
    result = db.execute(
        select(models.DailyProfitLog)
        .order_by(models.DailyProfitLog.date.desc())
        .limit(limit)
    )
    return result.scalars().all()





def get_min_transaction_year(db: Session):
    """Return the earliest year among all transactions (for the year selector)."""
    result = db.execute(
        select(func.strftime("%Y", models.Transaction.timestamp))
        .order_by(models.Transaction.timestamp)
        .limit(1)
    )
    year = result.scalar()
    return int(year) if year is not None else None


def get_monthly_days(db: Session, year: int, month: int):
    """Return daily income/expense/profit for a given month, excluding transfers."""
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    rows = db.execute(
        select(
            func.date(models.Transaction.timestamp).label("day"),
            models.Transaction.type,
            func.sum(models.Transaction.amount).label("total"),
        )
        .where(models.Transaction.timestamp >= month_start)
        .where(models.Transaction.timestamp < next_month)
        .where(models.Transaction.category != "Transfer")
        .group_by(func.date(models.Transaction.timestamp), models.Transaction.type)
        .order_by(func.date(models.Transaction.timestamp))
    )

    daily = {}
    for row in rows:
        d = row.day
        if d not in daily:
            daily[d] = {"income": 0, "expenses": 0}
        if row.type == "credit":
            daily[d]["income"] += row.total
        elif row.type == "debit":
            daily[d]["expenses"] += row.total

    return [
        {"date": d, "income": v["income"], "expenses": v["expenses"], "profit": v["income"] - v["expenses"]}
        for d, v in sorted(daily.items())
    ]


def get_monthly_overview(db: Session):
    """Return monthly income/expense/profit totals across all months, newest first."""
    rows = db.execute(
        select(
            func.strftime("%Y-%m", models.Transaction.timestamp).label("month"),
            models.Transaction.type,
            func.sum(models.Transaction.amount).label("total"),
        )
        .where(models.Transaction.category != "Transfer")
        .group_by(func.strftime("%Y-%m", models.Transaction.timestamp), models.Transaction.type)
        .order_by(func.strftime("%Y-%m", models.Transaction.timestamp).desc())
    )

    monthly = {}
    for row in rows:
        m = row.month
        if m not in monthly:
            monthly[m] = {"income": 0, "expenses": 0}
        if row.type == "credit":
            monthly[m]["income"] += row.total
        elif row.type == "debit":
            monthly[m]["expenses"] += row.total

    return [
        {"month": m, "income": v["income"], "expenses": v["expenses"], "profit": v["income"] - v["expenses"]}
        for m, v in monthly.items()
    ]


def get_debts(db: Session, status: str = None):
    """Return debts, optionally filtered by status (unpaid/paid), newest first."""
    query = select(models.Debt).order_by(models.Debt.created_at.desc())
    if status:
        query = query.where(models.Debt.status == status)
    result = db.execute(query)
    return result.scalars().all()


def get_debt(db: Session, debt_id: int):
    """Return a single debt by ID. Raises ValueError if not found."""
    debt = db.get(models.Debt, debt_id)
    if not debt:
        raise ValueError("Debt not found")
    return debt


def create_debt(db: Session, data: schemas.DebtCreate):
    """Create a new unpaid debt record. Parses ISO date string for due_date."""
    due = None
    if data.due_date:
        try:
            due = datetime.fromisoformat(data.due_date)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid due date format: {data.due_date}")
    debt = models.Debt(
        creditor=data.creditor,
        amount=data.amount,
        category=data.category,
        description=data.description,
        due_date=due,
        status="unpaid",
    )
    db.add(debt)
    db.flush()
    db.refresh(debt)
    return debt


def settle_debt(db: Session, debt_id: int, account_id: int):
    """Repay a debt by creating a repayment transaction from the given account.

    Marks the debt as paid and records settled_at.
    """
    debt = get_debt(db, debt_id)
    if debt.status == "paid":
        raise ValueError("Debt is already settled")

    account = get_account(db, account_id)
    if account.balance < debt.amount:
        raise ValueError("Insufficient balance")

    transaction = models.Transaction(
        account_id=account_id,
        type="repayment",
        amount=debt.amount,
        category=debt.category or "General",
        description=debt.description or f"Payment for {debt.creditor}",
        reference=f"debt:{debt.id}",
    )
    account.balance -= debt.amount
    debt.status = "paid"
    debt.settled_at = datetime.now(timezone.utc)

    db.add(transaction)
    db.flush()
    db.refresh(transaction)
    return debt, transaction


def receive_loan(db: Session, debt_id: int, account_id: int):
    """Receive a loan by creating a loan transaction into the given account.

    Records received_at on the debt. Does not change the debt status
    (remains unpaid until settled).
    """
    debt = get_debt(db, debt_id)
    if debt.status == "paid":
        raise ValueError("Debt is already paid")

    account = get_account(db, account_id)

    transaction = models.Transaction(
        account_id=account_id,
        type="loan",
        amount=debt.amount,
        category=debt.category or "General",
        description=debt.description or f"Loan received from {debt.creditor}",
        reference=f"debt:{debt.id}",
    )
    account.balance += debt.amount
    debt.received_at = datetime.now(timezone.utc)

    db.add(transaction)
    db.flush()
    db.refresh(transaction)
    return debt, transaction


def get_total_outstanding_debt(db: Session):
    """Return the sum of all unpaid debt amounts."""
    result = db.execute(
        select(func.coalesce(func.sum(models.Debt.amount), 0))
        .where(models.Debt.status == "unpaid")
    )
    return result.scalar()


def delete_debt(db: Session, debt_id: int):
    """Delete an unpaid debt. Raises ValueError if already paid."""
    debt = get_debt(db, debt_id)
    if debt.status == "paid":
        raise ValueError("Cannot delete a paid debt")
    db.delete(debt)
    db.flush()


def get_receivables(db: Session, status: str = None):
    """Return receivables, optionally filtered by status, newest first."""
    query = select(models.Receivable).order_by(models.Receivable.created_at.desc())
    if status:
        query = query.where(models.Receivable.status == status)
    result = db.execute(query)
    return result.scalars().all()


def get_receivable(db: Session, recv_id: int):
    """Return a single receivable by ID. Raises ValueError if not found."""
    recv = db.get(models.Receivable, recv_id)
    if not recv:
        raise ValueError("Receivable not found")
    return recv


def create_receivable(db: Session, data: schemas.ReceivableCreate):
    """Create a new unreceived receivable record. Parses ISO date string for due_date."""
    due = None
    if data.due_date:
        try:
            due = datetime.fromisoformat(data.due_date)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid due date format: {data.due_date}")
    recv = models.Receivable(
        debtor=data.debtor,
        amount=data.amount,
        category=data.category,
        description=data.description,
        due_date=due,
        status="unreceived",
    )
    db.add(recv)
    db.flush()
    db.refresh(recv)
    return recv


def receive_receivable(db: Session, recv_id: int, account_id: int):
    """Record receipt of a receivable payment into the given account.

    Creates a credit transaction and marks the receivable as received.
    """
    recv = get_receivable(db, recv_id)
    if recv.status == "received":
        raise ValueError("Receivable is already received")

    account = get_account(db, account_id)

    transaction = models.Transaction(
        account_id=account_id,
        type="credit",
        amount=recv.amount,
        category=recv.category or "General",
        description=recv.description or f"Payment from {recv.debtor}",
        reference=f"receivable:{recv.id}",
    )
    account.balance += recv.amount
    recv.status = "received"
    recv.received_at = datetime.now(timezone.utc)

    db.add(transaction)
    db.flush()
    db.refresh(transaction)
    return recv, transaction


def get_total_outstanding_receivable(db: Session):
    """Return the sum of all unreceived receivable amounts."""
    result = db.execute(
        select(func.coalesce(func.sum(models.Receivable.amount), 0))
        .where(models.Receivable.status == "unreceived")
    )
    return result.scalar()


def delete_receivable(db: Session, recv_id: int):
    """Delete an unreceived receivable. Raises ValueError if already received."""
    recv = get_receivable(db, recv_id)
    if recv.status == "received":
        raise ValueError("Cannot delete a received receivable")
    db.delete(recv)
    db.flush()


def update_account(db: Session, account_id: int, data: schemas.AccountCreate):
    """Update an account's name, type, and description."""
    account = get_account(db, account_id)
    # Pre-empt duplicate name collisions before flush
    if data.name != account.name:
        existing = db.execute(
            select(models.Account).where(models.Account.name == data.name)
        ).scalar_one_or_none()
        if existing:
            raise ValueError("An account with that name already exists")
    account.name = data.name
    account.type = data.type
    account.description = data.description
    db.flush()
    db.refresh(account)
    return account


def update_transaction(db: Session, transaction_id: int, data: schemas.TransactionCreate):
    """Update a transaction by reversing the old balance and applying the new one.

    Validates in order:
    1. Old transaction can be reversed (sufficient balance).
    2. Post-reversal balance supports the new transaction.
    3. Then applies both changes atomically.

    Transfer transactions and linked debt/receivable references are protected.
    """
    txn = get_transaction(db, transaction_id)

    # Block editing of transfer transactions (must delete and recreate)
    if txn.category == "Transfer":
        raise ValueError("Cannot edit transfer transactions")
    # Block setting Transfer on non-transfer transactions
    if data.category == "Transfer":
        raise ValueError("Cannot set category to Transfer on a non-transfer transaction")

    # Block account changes on linked transactions (debt, receivable, transfer)
    if data.account_id != txn.account_id and txn.reference:
        if txn.reference.startswith(("debt:", "receivable:", "xfer:")):
            raise ValueError("Cannot change account on a linked transaction")

    # Only block reference changes to reserved prefixes — allow preserving existing ones
    if data.reference:
        if data.reference.startswith(("debt:", "receivable:", "xfer:")):
            if txn.reference != data.reference:
                raise ValueError("Invalid reference format")
    else:
        if txn.reference and txn.reference.startswith(("debt:", "receivable:", "xfer:")):
            raise ValueError("Cannot clear reference on a linked transaction")

    old_account = txn.account
    old_type = txn.type
    old_amount = txn.amount

    if data.account_id != txn.account_id:
        new_account = get_account(db, data.account_id)
    else:
        new_account = old_account

    # Step 1: validate reversal is possible (before touching balances)
    if old_type in ("credit", "loan"):
        if old_account.balance < old_amount:
            raise ValueError("Cannot undo: insufficient balance to reverse credit")

    # Step 2: compute old account balance after reversal
    if old_type in ("credit", "loan"):
        old_post_reversal = old_account.balance - old_amount
    else:
        old_post_reversal = old_account.balance + old_amount

    # Step 3: validate new transaction against the post-reversal balance
    balance_for_new = old_post_reversal if new_account is old_account else new_account.balance
    if data.type in ("debit", "repayment") and balance_for_new < data.amount:
        raise ValueError("Insufficient balance")

    # Step 4: safe to apply — reverse old
    if old_type in ("credit", "loan"):
        old_account.balance -= old_amount
    else:
        old_account.balance += old_amount

    # Step 5: apply new
    if data.type in ("credit", "loan"):
        new_account.balance += data.amount
    else:
        new_account.balance -= data.amount

    txn.account_id = data.account_id
    txn.type = data.type
    txn.amount = data.amount
    txn.category = data.category
    txn.description = data.description
    txn.reference = data.reference

    db.flush()
    db.refresh(txn)
    return txn


def update_debt(db: Session, debt_id: int, data: schemas.DebtCreate):
    """Update a debt record.

    For paid debts: only metadata (creditor, category, description) can change.
    For unpaid debts: amount is locked once a loan has been received.
    """
    debt = get_debt(db, debt_id)

    if debt.status == "paid":
        debt.creditor = data.creditor
        debt.category = data.category
        debt.description = data.description
    else:
        # Prevent amount change if loan was already deposited
        existing_loan = db.execute(
            select(models.Transaction).where(
                models.Transaction.reference == f"debt:{debt_id}",
                models.Transaction.type == "loan",
            ).limit(1)
        ).scalar_one_or_none()
        if existing_loan and data.amount != debt.amount:
            raise ValueError("Cannot change amount after loan has been received")
        due = None
        if data.due_date:
            try:
                due = datetime.fromisoformat(data.due_date)
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid due date format: {data.due_date}")
        debt.creditor = data.creditor
        debt.amount = data.amount
        debt.category = data.category
        debt.description = data.description
        debt.due_date = due

    db.flush()
    db.refresh(debt)
    return debt


def update_receivable(db: Session, recv_id: int, data: schemas.ReceivableCreate):
    """Update a receivable record.

    For received receivables: only metadata (debtor, category, description) can change.
    """
    recv = get_receivable(db, recv_id)

    if recv.status == "received":
        recv.debtor = data.debtor
        recv.category = data.category
        recv.description = data.description
    else:
        due = None
        if data.due_date:
            try:
                due = datetime.fromisoformat(data.due_date)
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid due date format: {data.due_date}")
        recv.debtor = data.debtor
        recv.amount = data.amount
        recv.category = data.category
        recv.description = data.description
        recv.due_date = due

    db.flush()
    db.refresh(recv)
    return recv
