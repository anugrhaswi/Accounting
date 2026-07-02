from flask import Blueprint, redirect, render_template, request
from database import get_db
import crud
import schemas

bp = Blueprint("debts", __name__, url_prefix="/debts")


@bp.route("/")
def list_debts():
    db = get_db()
    status = request.args.get("status")
    debts = crud.get_debts(db, status=status)
    outstanding = crud.get_total_outstanding_debt(db)
    return render_template("debts.html", debts=debts, outstanding=outstanding, selected_status=status)


@bp.route("/", methods=["POST"])
def create_debt():
    db = get_db()
    form = request.form
    try:
        data = schemas.DebtCreate(
            creditor=form["creditor"],
            amount=float(form["amount"]),
            category=form.get("category") or "General",
            description=form.get("description") or None,
            due_date=form.get("due_date") or None,
        )
        crud.create_debt(db, data)
    except Exception:
        debts = crud.get_debts(db)
        outstanding = crud.get_total_outstanding_debt(db)
        return render_template("debts.html", debts=debts, outstanding=outstanding, error="Invalid input. Please check the form values."), 400
    return redirect("/debts/", 303)


@bp.route("/<int:debt_id>/settle")
def settle_debt_form(debt_id):
    db = get_db()
    try:
        debt = crud.get_debt(db, debt_id)
    except ValueError:
        return redirect("/debts/", 303)
    if debt.status == "paid":
        return redirect("/debts/", 303)
    accounts = crud.get_accounts(db)
    return render_template("debt_settle.html", debt=debt, accounts=accounts)


@bp.route("/<int:debt_id>/settle", methods=["POST"])
def settle_debt(debt_id):
    db = get_db()
    try:
        account_id = int(request.form["account_id"])
        crud.settle_debt(db, debt_id, account_id)
    except (ValueError, KeyError) as e:
        debt = crud.get_debt(db, debt_id)
        accounts = crud.get_accounts(db)
        return render_template("debt_settle.html", debt=debt, accounts=accounts, error=str(e)), 400
    return redirect("/debts/", 303)
