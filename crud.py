from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
import models
import schemas


async def get_accounts(db: AsyncSession):
    result = await db.execute(select(models.Account).order_by(models.Account.name))
    return result.scalars().all()


async def get_account(db: AsyncSession, account_id: int):
    account = await db.get(models.Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


async def create_account(db: AsyncSession, data: schemas.AccountCreate):
    account = models.Account(**data.model_dump())
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


async def delete_account(db: AsyncSession, account_id: int):
    account = await get_account(db, account_id)
    result = await db.execute(
        select(models.Transaction).where(models.Transaction.account_id == account_id).limit(1)
    )
    if result.first():
        raise HTTPException(status_code=400, detail="Cannot delete account with existing transactions")
    await db.delete(account)
    await db.flush()


async def get_total_balance(db: AsyncSession):
    result = await db.execute(select(func.coalesce(func.sum(models.Account.balance), 0)))
    return result.scalar()


async def get_setting(db: AsyncSession, key: str, default: str = None):
    result = await db.execute(
        select(models.Setting).where(models.Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting(db: AsyncSession, key: str, value: str):
    result = await db.execute(
        select(models.Setting).where(models.Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(models.Setting(key=key, value=value))
    await db.flush()


async def get_transactions(db: AsyncSession, account_id: int = None, txn_type: str = None, skip: int = 0, limit: int = 100):
    query = (
        select(models.Transaction)
        .options(selectinload(models.Transaction.account))
        .order_by(models.Transaction.timestamp.desc())
    )
    if account_id:
        query = query.where(models.Transaction.account_id == account_id)
    if txn_type:
        query = query.where(models.Transaction.type == txn_type)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


async def create_transaction(db: AsyncSession, data: schemas.TransactionCreate):
    account = await get_account(db, data.account_id)
    if data.type == "debit" and account.balance < data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    transaction = models.Transaction(**data.model_dump())
    if data.type == "credit":
        account.balance += data.amount
    else:
        account.balance -= data.amount
    db.add(transaction)
    await db.flush()
    await db.refresh(transaction)
    return transaction


async def transfer_money(db: AsyncSession, data: schemas.TransferCreate):
    if data.from_account_id == data.to_account_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account")

    from_account = await get_account(db, data.from_account_id)
    to_account = await get_account(db, data.to_account_id)

    if from_account.balance < data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    debit_txn = models.Transaction(
        account_id=data.from_account_id,
        type="debit",
        amount=data.amount,
        category="Transfer",
        description=data.description or f"Transfer to {to_account.name}",
    )
    from_account.balance -= data.amount

    credit_txn = models.Transaction(
        account_id=data.to_account_id,
        type="credit",
        amount=data.amount,
        category="Transfer",
        description=data.description or f"Transfer from {from_account.name}",
    )
    to_account.balance += data.amount

    db.add(debit_txn)
    db.add(credit_txn)
    await db.flush()
    await db.refresh(debit_txn)
    await db.refresh(credit_txn)
    return debit_txn, credit_txn


async def get_categories(db: AsyncSession, cat_type: str = None):
    query = select(models.Category).order_by(models.Category.sort_order, models.Category.name)
    if cat_type:
        query = query.where(models.Category.type == cat_type)
    result = await db.execute(query)
    return result.scalars().all()


async def create_category(db: AsyncSession, data: schemas.CategoryCreate):
    category = models.Category(**data.model_dump())
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, category_id: int):
    category = await db.get(models.Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    await db.delete(category)
    await db.flush()


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


async def seed_default_categories(db: AsyncSession):
    result = await db.execute(select(models.Category).limit(1))
    if result.first():
        return
    for cat in DEFAULT_CATEGORIES:
        db.add(models.Category(**cat))
    await db.flush()


async def get_daily_summary(db: AsyncSession, date: datetime = None):
    if date is None:
        date = datetime.now(timezone.utc)
    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    income = await db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "credit")
    )
    total_income = income.scalar()

    expenses = await db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "debit")
    )
    total_expenses = expenses.scalar()

    income_by_cat = await db.execute(
        select(models.Transaction.category, func.sum(models.Transaction.amount))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "credit")
        .group_by(models.Transaction.category)
    )

    expense_by_cat = await db.execute(
        select(models.Transaction.category, func.sum(models.Transaction.amount))
        .where(models.Transaction.timestamp >= day_start)
        .where(models.Transaction.timestamp < day_end)
        .where(models.Transaction.type == "debit")
        .group_by(models.Transaction.category)
    )

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "profit": total_income - total_expenses,
        "income_by_category": {r[0] or "General": r[1] for r in income_by_cat},
        "expense_by_category": {r[0] or "General": r[1] for r in expense_by_cat},
    }


async def get_monthly_days(db: AsyncSession, year: int, month: int):
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    rows = await db.execute(
        select(
            func.date(models.Transaction.timestamp).label("day"),
            models.Transaction.type,
            func.sum(models.Transaction.amount).label("total"),
        )
        .where(models.Transaction.timestamp >= month_start)
        .where(models.Transaction.timestamp < next_month)
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


async def get_monthly_overview(db: AsyncSession):
    rows = await db.execute(
        select(
            func.strftime("%Y-%m", models.Transaction.timestamp).label("month"),
            models.Transaction.type,
            func.sum(models.Transaction.amount).label("total"),
        )
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
