from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request
from database import get_db
import crud
import schemas

bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@bp.route("/new")
def new_transaction_form():
    db = get_db()
    account_id = request.args.get("account_id", type=int)
    accounts = crud.get_accounts(db)
    income_categories = crud.get_categories(db, cat_type="income")
    expense_categories = crud.get_categories(db, cat_type="expense")
    return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, selected_account_id=account_id)


@bp.route("/", methods=["POST"])
def create_transaction():
    db = get_db()
    form = request.form
    try:
        data = schemas.TransactionCreate(
            account_id=int(form["account_id"]),
            type=form["type"],
            amount=float(form["amount"]),
            category=form.get("category") or "General",
            description=form.get("description") or None,
            reference=form.get("reference") or None,
        )
        crud.create_transaction(db, data)
    except ValueError as e:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, error=str(e)), 400
    except Exception:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, error="Invalid input. Please check the form values."), 400
    return redirect("/", 303)


@bp.route("/transfer")
def transfer_form():
    db = get_db()
    accounts = crud.get_accounts(db)
    return render_template("transfer_form.html", accounts=accounts)


@bp.route("/transfer", methods=["POST"])
def transfer_money():
    db = get_db()
    form = request.form
    data = schemas.TransferCreate(
        from_account_id=int(form["from_account_id"]),
        to_account_id=int(form["to_account_id"]),
        amount=float(form["amount"]),
        description=form.get("description") or None,
    )
    try:
        crud.transfer_money(db, data)
    except ValueError as e:
        accounts = crud.get_accounts(db)
        return render_template("transfer_form.html", accounts=accounts, error=str(e)), 400
    return redirect("/", 303)


@bp.route("/<int:transaction_id>/delete", methods=["POST"])
def delete_transaction(transaction_id):
    db = get_db()
    try:
        crud.delete_transaction(db, transaction_id)
    except ValueError as e:
        return redirect(f"/logs?error={quote(str(e))}", 303)
    referrer = request.headers.get("Referer", "/logs")
    return redirect(referrer, 303)
