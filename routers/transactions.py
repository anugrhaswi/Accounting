from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import RedirectResponse
from database import get_db
from templating import templates
import crud
import schemas

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/new")
async def new_transaction_form(request: Request, db: AsyncSession = Depends(get_db), account_id: Optional[int] = None):
    accounts = await crud.get_accounts(db)
    income_categories = await crud.get_categories(db, cat_type="income")
    expense_categories = await crud.get_categories(db, cat_type="expense")
    return templates.TemplateResponse(request, "transaction_form.html", {
        "accounts": accounts,
        "income_categories": income_categories,
        "expense_categories": expense_categories,
        "selected_account_id": account_id,
    })


@router.post("/")
async def create_transaction(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    try:
        data = schemas.TransactionCreate(
            account_id=int(form["account_id"]),
            type=form["type"],
            amount=float(form["amount"]),
            category=form.get("category") or "General",
            description=form.get("description") or None,
            reference=form.get("reference") or None,
        )
        await crud.create_transaction(db, data)
    except HTTPException as e:
        accounts = await crud.get_accounts(db)
        income_categories = await crud.get_categories(db, cat_type="income")
        expense_categories = await crud.get_categories(db, cat_type="expense")
        return templates.TemplateResponse(request, "transaction_form.html", {
            "accounts": accounts,
            "income_categories": income_categories,
            "expense_categories": expense_categories,
            "error": e.detail,
        }, status_code=400)
    except Exception:
        accounts = await crud.get_accounts(db)
        income_categories = await crud.get_categories(db, cat_type="income")
        expense_categories = await crud.get_categories(db, cat_type="expense")
        return templates.TemplateResponse(request, "transaction_form.html", {
            "accounts": accounts,
            "income_categories": income_categories,
            "expense_categories": expense_categories,
            "error": "Invalid input. Please check the form values.",
        }, status_code=400)
    return RedirectResponse(url="/", status_code=303)


@router.get("/transfer")
async def transfer_form(request: Request, db: AsyncSession = Depends(get_db)):
    accounts = await crud.get_accounts(db)
    return templates.TemplateResponse(request, "transfer_form.html", {
        "accounts": accounts,
    })


@router.post("/transfer")
async def transfer_money(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    data = schemas.TransferCreate(
        from_account_id=int(form["from_account_id"]),
        to_account_id=int(form["to_account_id"]),
        amount=float(form["amount"]),
        description=form.get("description") or None,
    )
    try:
        await crud.transfer_money(db, data)
    except HTTPException as e:
        accounts = await crud.get_accounts(db)
        return templates.TemplateResponse(request, "transfer_form.html", {
            "accounts": accounts,
            "error": e.detail,
        }, status_code=400)
    return RedirectResponse(url="/", status_code=303)
