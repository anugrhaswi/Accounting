from datetime import datetime, timezone
from flask import Blueprint, render_template, request
from database import get_db
import crud

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
def reports_page():
    db = get_db()
    now = datetime.now(timezone.utc)

    year_arg = request.args.get("year")
    month_arg = request.args.get("month")
    try:
        year = int(year_arg) if year_arg else now.year
    except (ValueError, TypeError):
        year = now.year
    try:
        month = int(month_arg) if month_arg else now.month
    except (ValueError, TypeError):
        month = now.month
    if month < 1 or month > 12:
        month = now.month

    monthly_overview = crud.get_monthly_overview(db)
    daily = crud.get_monthly_days(db, year, month)

    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    years = list(range(now.year - 5, now.year + 1))

    return render_template("reports.html", daily=daily, monthly=monthly_overview, selected_year=year, selected_month=month, selected_month_name=month_names[month], years=years, month_names=month_names)
