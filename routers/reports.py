"""Reporting routes — P&L reports and daily profit log at /reports/..."""

from datetime import date, datetime, timezone, timedelta
from flask import Blueprint, render_template, request
from database import get_db
import crud

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
def reports_page():
    """Show the P&L report page with daily breakdown for a selected month and monthly overview.

    Profit = total_balance - fixed_capital.
    Net worth = total_balance + outstanding_receivable - outstanding_debt.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    year_arg = request.args.get("year")
    month_arg = request.args.get("month")
    try:
        year = int(year_arg) if year_arg else now.year
    except (ValueError, TypeError):
        year = now.year
    year = max(2000, min(year, 2100))
    try:
        month = int(month_arg) if month_arg else now.month
    except (ValueError, TypeError):
        month = now.month
    if month < 1 or month > 12:
        month = now.month

    daily = crud.get_monthly_days(db, year, month)
    monthly_overview = crud.get_monthly_overview(db)

    total_balance = crud.get_total_balance(db)
    try:
        fixed_capital = float(crud.get_setting(db, "fixed_capital", "0"))
    except (ValueError, TypeError):
        fixed_capital = 0.0
    profit = total_balance - fixed_capital
    outstanding_debt = crud.get_total_outstanding_debt(db)
    outstanding_receivable = crud.get_total_outstanding_receivable(db)
    reports_net_worth = total_balance + outstanding_receivable - outstanding_debt

    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    min_year = crud.get_min_transaction_year(db) or now.year
    years = list(range(min_year, now.year + 1))

    return render_template("reports.html", daily=daily, monthly=monthly_overview,
                           selected_year=year, selected_month=month,
                           selected_month_name=month_names[month], years=years,
                           month_names=month_names, profit=profit,
                           outstanding_debt=outstanding_debt,
                           outstanding_receivable=outstanding_receivable,
                           reports_net_worth=reports_net_worth)


@bp.route("/profits")
def profits_page():
    """Show the daily profit log with running total, oldest to newest."""
    db = get_db()
    logs = crud.get_daily_profit_logs(db, limit=365)

    logs_list = list(logs)
    logs_list.reverse()
    running = 0.0
    logs_with_running = []
    for entry in logs_list:
        running += entry.profit
        logs_with_running.append({
            "date": entry.date.isoformat(),
            "profit": entry.profit,
            "running": running,
        })
    return render_template("profits.html", logs=logs_with_running)
