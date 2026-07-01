from urllib.parse import quote

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import RedirectResponse
from database import get_db
from templating import templates
import crud
import schemas

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/")
async def list_categories(request: Request, db: AsyncSession = Depends(get_db), error: Optional[str] = Query(default=None)):
    income_categories = await crud.get_categories(db, cat_type="income")
    expense_categories = await crud.get_categories(db, cat_type="expense")
    return templates.TemplateResponse(request, "categories.html", {
        "income_categories": income_categories,
        "expense_categories": expense_categories,
        "error": error,
    })


@router.post("/")
async def create_category(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    try:
        data = schemas.CategoryCreate(
            name=form["name"],
            type=form["type"],
        )
        await crud.create_category(db, data)
    except Exception:
        income_categories = await crud.get_categories(db, cat_type="income")
        expense_categories = await crud.get_categories(db, cat_type="expense")
        return templates.TemplateResponse(request, "categories.html", {
            "income_categories": income_categories,
            "expense_categories": expense_categories,
            "error": "A category with this name already exists.",
        }, status_code=400)
    return RedirectResponse(url="/categories/", status_code=303)


@router.post("/{category_id}/delete")
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_category(db, category_id)
    except HTTPException as e:
        return RedirectResponse(url=f"/categories/?error={quote(str(e.detail))}", status_code=303)
    return RedirectResponse(url="/categories/", status_code=303)
