from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from templating import templates
import crud

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/")
async def reports_page(
    request: Request,
    year: int = None,
    month: int = None,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    monthly_overview = await crud.get_monthly_overview(db)
    daily = await crud.get_monthly_days(db, year, month)

    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    years = list(range(now.year - 5, now.year + 1))

    return templates.TemplateResponse(request, "reports.html", {
        "daily": daily,
        "monthly": monthly_overview,
        "selected_year": year,
        "selected_month": month,
        "selected_month_name": month_names[month],
        "years": years,
        "month_names": month_names,
    })
