import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import models
import schemas
from schemas import asdict


def get_accounts(db: Session):
    result = db.execute(select(models.Account).order_by(models.Account.name))
    return result.scalars().all()


def get_account(db: Session, account_id: int):
    account = db.get(models.Account, account_id)
    if not account:
        raise ValueError("Account not found")
    return account


def create_account(db: Session, data: schemas.AccountCreate):
    account = models.Account(**asdict(data))
    db.add(account)
    db.flush()
    db.refresh(account)
    return account


def delete_account(db: Session, account_id: int):
    account = get_account(db, account_id)
    result = db.execute(
        select(models.Transaction).where(models.Transaction.account_id == account_id).limit(1)
    )
    if result.first():
        raise ValueError("Cannot delete account with existing transactions")
    db.delete(account)
    db.flush()


def get_total_balance(db: Session):
    result = db.execute(select(func.coalesce(func.sum(models.Account.balance), 0)))
    return result.scalar()


def get_setting(db: Session, key: str, default: str = None):
    result = db.execute(
        select(models.Setting).where(models.Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting and setting.value is not None else default


def set_setting(db: Session, key: str, value: str):
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
    account = get_account(db, data.account_id)
    if data.type == "debit" and account.balance < data.amount:
        raise ValueError("Insufficient balance")
    transaction = models.Transaction(**asdict(data))
    if data.type == "credit":
        account.balance += data.amount
    else:
        account.balance -= data.amount
    db.add(transaction)
    db.flush()
    db.refresh(transaction)
    return transaction


def get_transaction(db: Session, transaction_id: int):
    txn = db.get(models.Transaction, transaction_id)
    if not txn:
        raise ValueError("Transaction not found")
    return txn


def delete_transaction(db: Session, transaction_id: int):
    txn = get_transaction(db, transaction_id)
    account = txn.account

    if txn.category == "Transfer" and txn.reference and txn.reference.startswith("xfer:"):
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

        if txn.type == "debit":
            account.balance += txn.amount
        else:
            if account.balance < txn.amount:
                raise ValueError("Cannot undo: insufficient balance to reverse credit")
            account.balance -= txn.amount

        db.delete(txn)
        db.flush()
        return

    if txn.type == "credit":
        if account.balance < txn.amount:
            raise ValueError("Cannot undo: insufficient balance to reverse credit")
        account.balance -= txn.amount
    else:
        account.balance += txn.amount

    if txn.reference and txn.reference.startswith("debt:"):
        try:
            debt_id = int(txn.reference.split(":", 1)[1])
            debt = db.get(models.Debt, debt_id)
            if debt and debt.status == "paid":
                debt.status = "unpaid"
                debt.settled_at = None
        except (ValueError, TypeError):
            pass

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
    query = select(models.Category).order_by(models.Category.sort_order, models.Category.name)
    if cat_type:
        query = query.where(models.Category.type == cat_type)
    result = db.execute(query)
    return result.scalars().all()


def create_category(db: Session, data: schemas.CategoryCreate):
    category = models.Category(**asdict(data))
    db.add(category)
    db.flush()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: int):
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
    result = db.execute(select(models.Category).limit(1))
    if result.first():
        return
    for cat in DEFAULT_CATEGORIES:
        db.add(models.Category(**cat))
    db.flush()


def get_daily_summary(db: Session, date: datetime = None):
    if date is None:
        date = datetime.now(timezone.utc)
    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    income = db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "credit")
        .where(models.Transaction.category != "Transfer")
    )
    total_income = income.scalar()

    expenses = db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "debit")
        .where(models.Transaction.category != "Transfer")
    )
    total_expenses = expenses.scalar()

    income_by_cat = db.execute(
        select(models.Transaction.category, func.sum(models.Transaction.amount))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "credit")
        .where(models.Transaction.category != "Transfer")
        .group_by(models.Transaction.category)
    )

    expense_by_cat = db.execute(
        select(models.Transaction.category, func.sum(models.Transaction.amount))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "debit")
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


def update_daily_profit_log(db: Session, date: datetime):
    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    income = db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "credit")
        .where(models.Transaction.category != "Transfer")
    ).scalar()

    expenses = db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "debit")
        .where(models.Transaction.category != "Transfer")
    ).scalar()

    new_debts = db.execute(
        select(func.coalesce(func.sum(models.Debt.amount), 0))
        .where(models.Debt.created_at >= day_start)
        .where(models.Debt.created_at < day_end)
    ).scalar()

    settled_debts = db.execute(
        select(func.coalesce(func.sum(models.Debt.amount), 0))
        .where(models.Debt.settled_at >= day_start)
        .where(models.Debt.settled_at < day_end)
        .where(models.Debt.status == "paid")
    ).scalar()

    new_receivables = db.execute(
        select(func.coalesce(func.sum(models.Receivable.amount), 0))
        .where(models.Receivable.created_at >= day_start)
        .where(models.Receivable.created_at < day_end)
    ).scalar()

    received_receivables = db.execute(
        select(func.coalesce(func.sum(models.Receivable.amount), 0))
        .where(models.Receivable.received_at >= day_start)
        .where(models.Receivable.received_at < day_end)
        .where(models.Receivable.status == "received")
    ).scalar()

    try:
        today_capital = float(get_setting(db, "fixed_capital", "0"))
    except (ValueError, TypeError):
        today_capital = 0.0

    day_key = day_start.date()
    yesterday_entry = db.execute(
        select(models.DailyProfitLog)
        .where(models.DailyProfitLog.date < day_key)
        .order_by(models.DailyProfitLog.date.desc())
        .limit(1)
    ).scalar_one_or_none()
    yesterday_capital = yesterday_entry.capital if yesterday_entry else today_capital
    capital_delta = today_capital - yesterday_capital

    net_receivable = new_receivables - received_receivables
    net_debt = new_debts - settled_debts
    profit = income - expenses + net_receivable - net_debt - capital_delta

    existing = db.execute(
        select(models.DailyProfitLog).where(models.DailyProfitLog.date == day_key)
    ).scalar_one_or_none()

    if existing:
        existing.income = income
        existing.expenses = expenses
        existing.new_debts = new_debts
        existing.settled_debts = settled_debts
        existing.new_receivables = new_receivables
        existing.received_receivables = received_receivables
        existing.capital = today_capital
        existing.capital_delta = capital_delta
        existing.profit = profit
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(models.DailyProfitLog(
            date=day_key, income=income, expenses=expenses,
            new_debts=new_debts, settled_debts=settled_debts,
            new_receivables=new_receivables, received_receivables=received_receivables,
            capital=today_capital, capital_delta=capital_delta, profit=profit,
        ))
    db.flush()


def get_daily_profit_logs(db: Session, limit: int = 365):
    result = db.execute(
        select(models.DailyProfitLog)
        .order_by(models.DailyProfitLog.date.desc())
        .limit(limit)
    )
    return result.scalars().all()


def backfill_daily_profit_logs(db: Session):
    first_txn = db.execute(
        select(func.date(func.min(models.Transaction.timestamp)))
    ).scalar()
    if not first_txn:
        return
    first_date = datetime.strptime(first_txn, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    cursor = first_date
    while cursor < today:
        update_daily_profit_log(db, cursor)
        cursor += timedelta(days=1)
    db.flush()


def get_monthly_days(db: Session, year: int, month: int):
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
        else:
            daily[d]["expenses"] += row.total

    return [
        {"date": d, "income": v["income"], "expenses": v["expenses"], "profit": v["income"] - v["expenses"]}
        for d, v in sorted(daily.items())
    ]


def get_monthly_overview(db: Session):
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
        else:
            monthly[m]["expenses"] += row.total

    return [
        {"month": m, "income": v["income"], "expenses": v["expenses"], "profit": v["income"] - v["expenses"]}
        for m, v in sorted(monthly.items(), reverse=True)
    ]


def get_debts(db: Session, status: str = None):
    query = select(models.Debt).order_by(models.Debt.created_at.desc())
    if status:
        query = query.where(models.Debt.status == status)
    result = db.execute(query)
    return result.scalars().all()


def get_debt(db: Session, debt_id: int):
    debt = db.get(models.Debt, debt_id)
    if not debt:
        raise ValueError("Debt not found")
    return debt


def create_debt(db: Session, data: schemas.DebtCreate):
    due = None
    if data.due_date:
        try:
            due = datetime.fromisoformat(data.due_date)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
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
    debt = get_debt(db, debt_id)
    if debt.status == "paid":
        raise ValueError("Debt is already settled")

    account = get_account(db, account_id)
    if account.balance < debt.amount:
        raise ValueError("Insufficient balance")

    transaction = models.Transaction(
        account_id=account_id,
        type="debit",
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


def get_total_outstanding_debt(db: Session):
    result = db.execute(
        select(func.coalesce(func.sum(models.Debt.amount), 0))
        .where(models.Debt.status == "unpaid")
    )
    return result.scalar()


def delete_debt(db: Session, debt_id: int):
    debt = get_debt(db, debt_id)
    if debt.status == "paid":
        raise ValueError("Cannot delete a paid debt")
    db.delete(debt)
    db.flush()


def get_receivables(db: Session, status: str = None):
    query = select(models.Receivable).order_by(models.Receivable.created_at.desc())
    if status:
        query = query.where(models.Receivable.status == status)
    result = db.execute(query)
    return result.scalars().all()


def get_receivable(db: Session, recv_id: int):
    recv = db.get(models.Receivable, recv_id)
    if not recv:
        raise ValueError("Receivable not found")
    return recv


def create_receivable(db: Session, data: schemas.ReceivableCreate):
    due = None
    if data.due_date:
        try:
            due = datetime.fromisoformat(data.due_date)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
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
    result = db.execute(
        select(func.coalesce(func.sum(models.Receivable.amount), 0))
        .where(models.Receivable.status == "unreceived")
    )
    return result.scalar()


def delete_receivable(db: Session, recv_id: int):
    recv = get_receivable(db, recv_id)
    if recv.status == "received":
        raise ValueError("Cannot delete a received receivable")
    db.delete(recv)
    db.flush()
