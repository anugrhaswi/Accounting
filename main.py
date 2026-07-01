from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from contextlib import asynccontextmanager
from database import engine, Base, async_session, get_db
from templating import templates
from routers import accounts, categories, transactions, reports
import crud


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        result = await conn.execute(text("PRAGMA table_info(transactions)"))
        cols = [r[1] for r in result]
        if "category" not in cols:
            await conn.execute(text("ALTER TABLE transactions ADD COLUMN category VARCHAR(50)"))
    async with async_session() as session:
        async with session.begin():
            await crud.seed_default_categories(session)
    yield


app = FastAPI(title="CSC Shop Accounting", lifespan=lifespan)

app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(reports.router)


@app.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db), error: Optional[str] = Query(default=None)):
    accounts_list = await crud.get_accounts(db)
    summary = await crud.get_daily_summary(db)
    total_balance = await crud.get_total_balance(db)
    try:
        fixed_capital = float(await crud.get_setting(db, "fixed_capital", "0"))
    except (ValueError, TypeError):
        fixed_capital = 0.0
    net_profit = total_balance - fixed_capital
    return templates.TemplateResponse(request, "index.html", {
        "accounts": accounts_list,
        "summary": summary,
        "total_balance": total_balance,
        "fixed_capital": fixed_capital,
        "net_profit": net_profit,
        "error": error,
    })


@app.post("/settings/capital")
async def update_capital(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    value = form.get("fixed_capital", "0")
    try:
        float(value)
    except (ValueError, TypeError):
        value = "0"
    await crud.set_setting(db, "fixed_capital", value)
    return RedirectResponse(url="/", status_code=303)


@app.get("/logs")
async def view_logs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    account_id: Optional[int] = None,
    txn_type: Optional[str] = Query(default=None, alias="type"),
):
    accounts = await crud.get_accounts(db)
    transactions_list = await crud.get_transactions(db, account_id=account_id, txn_type=txn_type, limit=200)
    return templates.TemplateResponse(request, "logs.html", {
        "accounts": accounts,
        "transactions": transactions_list,
        "selected_account_id": account_id,
        "selected_type": txn_type,
    })
