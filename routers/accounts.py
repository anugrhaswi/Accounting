from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import RedirectResponse
from database import get_db
from templating import templates
import crud
import schemas

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/new")
async def new_account_form(request: Request):
    return templates.TemplateResponse(request, "account_form.html")


@router.post("/")
async def create_account(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    data = schemas.AccountCreate(**form)
    try:
        await crud.create_account(db, data)
    except Exception:
        return templates.TemplateResponse(request, "account_form.html", {
            "error": "An account with this name already exists.",
        }, status_code=400)
    return RedirectResponse(url="/", status_code=303)


@router.post("/{account_id}/delete")
async def delete_account(account_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_account(db, account_id)
    except HTTPException as e:
        return RedirectResponse(url=f"/?error={quote(str(e.detail))}", status_code=303)
    return RedirectResponse(url="/", status_code=303)
