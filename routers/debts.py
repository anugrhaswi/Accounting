"""Debt management routes (CRUD at /debts/...) plus loan receive/settle.

Debt lifecycle: create (unpaid) → receive loan into an account → settle from an account (paid).
"""

import math
from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request
from sqlalchemy.exc import IntegrityError
from database import get_db
import crud
import schemas

bp = Blueprint("debts", __name__, url_prefix="/debts")


@bp.route("/")
def list_debts():
    """Show the debts list page with optional status filter and outstanding total."""
    db = get_db()
    error = request.args.get("error")
    status = request.args.get("status")
    debts = crud.get_debts(db, status=status)
    outstanding = crud.get_total_outstanding_debt(db)
    return render_template("debts.html", debts=debts, outstanding=outstanding, selected_status=status, error=error)


@bp.route("/", methods=["POST"])
def create_debt():
    """Handle debt creation from form submission."""
    db = get_db()
    form = request.form
    try:
        amount = float(form["amount"])
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
        data = schemas.DebtCreate(
            creditor=form["creditor"].strip(),
            amount=amount,
            category=(form.get("category") or "").strip() or "General",
            description=(form.get("description") or "").strip() or None,
            due_date=(form.get("due_date") or "").strip() or None,
        )
        crud.create_debt(db, data)
    except (ValueError, TypeError) as e:
        debts = crud.get_debts(db)
        outstanding = crud.get_total_outstanding_debt(db)
        form_values = {"creditor": form.get("creditor", ""), "amount": form.get("amount", ""),
                       "category": form.get("category", ""), "description": form.get("description", ""),
                       "due_date": form.get("due_date", "")}
        return render_template("debts.html", debts=debts, outstanding=outstanding, error=str(e), form_values=form_values), 400
    except IntegrityError:
        debts = crud.get_debts(db)
        outstanding = crud.get_total_outstanding_debt(db)
        form_values = {"creditor": form.get("creditor", ""), "amount": form.get("amount", ""),
                       "category": form.get("category", ""), "description": form.get("description", ""),
                       "due_date": form.get("due_date", "")}
        return render_template("debts.html", debts=debts, outstanding=outstanding, error="A database constraint was violated. Check the values.", form_values=form_values), 400
    except Exception:
        debts = crud.get_debts(db)
        outstanding = crud.get_total_outstanding_debt(db)
        form_values = {"creditor": form.get("creditor", ""), "amount": form.get("amount", ""),
                       "category": form.get("category", ""), "description": form.get("description", ""),
                       "due_date": form.get("due_date", "")}
        return render_template("debts.html", debts=debts, outstanding=outstanding, error="Invalid input. Please check the form values.", form_values=form_values), 400
    return redirect("/debts/", 303)


@bp.route("/<int:debt_id>/receive")
def receive_loan_form(debt_id):
    """Show the form to receive a loan into an account."""
    db = get_db()
    try:
        debt = crud.get_debt(db, debt_id)
    except ValueError:
        return redirect("/debts/", 303)
    if debt.status == "paid":
        return redirect("/debts/", 303)
    if debt.received_at:
        return redirect("/debts/", 303)
    accounts = crud.get_accounts(db)
    return render_template("debt_receive.html", debt=debt, accounts=accounts)


@bp.route("/<int:debt_id>/receive", methods=["POST"])
def receive_loan(debt_id):
    """Handle loan receipt into a selected account."""
    db = get_db()
    try:
        account_id = int(request.form["account_id"])
    except (ValueError, TypeError):
        try:
            debt = crud.get_debt(db, debt_id)
            accounts = crud.get_accounts(db)
        except ValueError:
            return redirect("/debts/", 303)
        return render_template("debt_receive.html", debt=debt, accounts=accounts, error="Invalid numeric value."), 400
    try:
        crud.receive_loan(db, debt_id, account_id)
    except (ValueError, KeyError) as e:
        try:
            debt = crud.get_debt(db, debt_id)
            accounts = crud.get_accounts(db)
        except ValueError:
            return redirect("/debts/", 303)
        return render_template("debt_receive.html", debt=debt, accounts=accounts, error=str(e)), 400
    return redirect("/debts/", 303)


@bp.route("/<int:debt_id>/settle")
def settle_debt_form(debt_id):
    """Show the form to settle (repay) a debt from an account."""
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
    """Handle debt repayment from a selected account."""
    db = get_db()
    try:
        account_id = int(request.form["account_id"])
    except (ValueError, TypeError):
        try:
            debt = crud.get_debt(db, debt_id)
            accounts = crud.get_accounts(db)
        except ValueError:
            return redirect("/debts/", 303)
        return render_template("debt_settle.html", debt=debt, accounts=accounts, error="Invalid numeric value."), 400
    try:
        crud.settle_debt(db, debt_id, account_id)
    except (ValueError, KeyError) as e:
        try:
            debt = crud.get_debt(db, debt_id)
            accounts = crud.get_accounts(db)
        except ValueError:
            return redirect("/debts/", 303)
        return render_template("debt_settle.html", debt=debt, accounts=accounts, error=str(e)), 400
    return redirect("/debts/", 303)


@bp.route("/<int:debt_id>/edit")
def edit_debt_form(debt_id):
    """Show the debt edit form pre-filled with existing data."""
    db = get_db()
    try:
        debt = crud.get_debt(db, debt_id)
    except ValueError:
        return redirect("/debts/", 303)
    return render_template("debt_edit.html", debt=debt)


@bp.route("/<int:debt_id>/edit", methods=["POST"])
def edit_debt(debt_id):
    """Handle debt update from form submission.

    For paid debts: only metadata (creditor, category, description) may change.
    For unpaid debts: amount is locked once a loan has been received.
    """
    db = get_db()
    form = request.form
    try:
        data = schemas.DebtCreate(
            creditor=form["creditor"].strip(),
            amount=float(form["amount"]),
            category=(form.get("category") or "").strip() or "General",
            description=(form.get("description") or "").strip() or None,
            due_date=(form.get("due_date") or "").strip() or None,
        )
        crud.update_debt(db, debt_id, data)
    except ValueError as e:
        try:
            debt = crud.get_debt(db, debt_id)
        except ValueError:
            return redirect("/debts/", 303)
        return render_template("debt_edit.html", debt=debt, error=str(e)), 400
    except IntegrityError:
        try:
            debt = crud.get_debt(db, debt_id)
        except ValueError:
            return redirect("/debts/", 303)
        return render_template("debt_edit.html", debt=debt, error="A database constraint was violated. Check the values."), 400
    except Exception:
        try:
            debt = crud.get_debt(db, debt_id)
        except ValueError:
            return redirect("/debts/", 303)
        return render_template("debt_edit.html", debt=debt, error="Invalid input. Please check the form values."), 400
    return redirect("/debts/", 303)


@bp.route("/<int:debt_id>/delete", methods=["POST"])
def delete_debt(debt_id):
    """Delete an unpaid debt. Paid debts cannot be deleted."""
    db = get_db()
    try:
        crud.delete_debt(db, debt_id)
    except ValueError as e:
        return redirect(f"/debts/?error={quote(str(e))}", 303)
    return redirect("/debts/", 303)
