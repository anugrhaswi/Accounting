"""Transaction management routes (CRUD at /transactions/...) plus transfer.

Transfer transactions (category = "Transfer") are created via the dedicated
/transactions/transfer endpoint and cannot be directly created or edited.
"""

from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request
from sqlalchemy.exc import IntegrityError
from database import get_db
import crud
import schemas

bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@bp.route("/new")
def new_transaction_form():
    """Show the transaction creation form with account and category dropdowns."""
    db = get_db()
    account_id = request.args.get("account_id", type=int)
    accounts = crud.get_accounts(db)
    income_categories = crud.get_categories(db, cat_type="income")
    expense_categories = crud.get_categories(db, cat_type="expense")
    return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, selected_account_id=account_id)


@bp.route("/", methods=["POST"])
def create_transaction():
    """Handle transaction creation from form submission.

    Validates numeric fields before creating the schema object.
    Blocks direct creation of Transfer category and reserved reference prefixes.
    """
    db = get_db()
    form = request.form
    try:
        account_id = int(form["account_id"])
        amount = float(form["amount"])
    except (ValueError, TypeError):
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, error="Invalid numeric value. Check the amount and account fields."), 400
    try:
        data = schemas.TransactionCreate(
            account_id=account_id,
            type=form["type"].strip(),
            amount=amount,
            category=(form.get("category") or "").strip() or "General",
            description=(form.get("description") or "").strip() or None,
            reference=(form.get("reference") or "").strip() or None,
        )
        crud.create_transaction(db, data)
    except ValueError as e:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, error=str(e)), 400
    except IntegrityError:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, error="A database constraint was violated. Check the values."), 400
    except Exception:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, error="Invalid input. Please check the form values."), 400
    try: crud.backfill_daily_profit_logs(db)
    except Exception as e: print(f"backfill error: {e}")
    return redirect("/", 303)


@bp.route("/transfer")
def transfer_form():
    """Show the money transfer form with from/to account dropdowns."""
    db = get_db()
    accounts = crud.get_accounts(db)
    return render_template("transfer_form.html", accounts=accounts)


@bp.route("/transfer", methods=["POST"])
def transfer_money():
    """Handle money transfer between two accounts.

    Creates a paired debit (from) and credit (to) transaction.
    """
    db = get_db()
    form = request.form
    try:
        from_account_id = int(form["from_account_id"])
        to_account_id = int(form["to_account_id"])
        amount = float(form["amount"])
    except (ValueError, TypeError):
        accounts = crud.get_accounts(db)
        return render_template("transfer_form.html", accounts=accounts, error="Invalid numeric value. Check the amount and account fields."), 400
    try:
        data = schemas.TransferCreate(
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=amount,
            description=(form.get("description") or "").strip() or None,
        )
        crud.transfer_money(db, data)
    except (ValueError, KeyError) as e:
        accounts = crud.get_accounts(db)
        return render_template("transfer_form.html", accounts=accounts, error=str(e)), 400
    try: crud.backfill_daily_profit_logs(db)
    except Exception as e: print(f"backfill error: {e}")
    return redirect("/", 303)


@bp.route("/<int:transaction_id>/edit")
def edit_transaction_form(transaction_id):
    """Show the transaction edit form pre-filled with existing data."""
    db = get_db()
    try:
        txn = crud.get_transaction(db, transaction_id)
    except ValueError:
        return redirect("/logs", 303)
    accounts = crud.get_accounts(db)
    income_categories = crud.get_categories(db, cat_type="income")
    expense_categories = crud.get_categories(db, cat_type="expense")
    return render_template("transaction_form.html", accounts=accounts,
                           income_categories=income_categories,
                           expense_categories=expense_categories, txn=txn)


@bp.route("/<int:transaction_id>/edit", methods=["POST"])
def edit_transaction(transaction_id):
    """Handle transaction update from form submission.

    Reverses the old balance change and applies the new one atomically.
    Transfer transactions and linked debt/receivable references are protected.
    """
    db = get_db()
    form = request.form
    try:
        account_id = int(form["account_id"])
        amount = float(form["amount"])
    except (ValueError, TypeError):
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        try:
            txn = crud.get_transaction(db, transaction_id)
        except ValueError:
            return redirect("/logs", 303)
        return render_template("transaction_form.html", accounts=accounts, income_categories=income_categories, expense_categories=expense_categories, txn=txn, error="Invalid numeric value. Check the amount and account fields."), 400
    try:
        data = schemas.TransactionCreate(
            account_id=account_id,
            type=form["type"].strip(),
            amount=amount,
            category=(form.get("category") or "").strip() or "General",
            description=(form.get("description") or "").strip() or None,
            reference=(form.get("reference") or "").strip() or None,
        )
        crud.update_transaction(db, transaction_id, data)
    except ValueError as e:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        try:
            txn = crud.get_transaction(db, transaction_id)
        except ValueError:
            return redirect("/logs", 303)
        return render_template("transaction_form.html", accounts=accounts,
                               income_categories=income_categories,
                               expense_categories=expense_categories, txn=txn, error=str(e)), 400
    except IntegrityError:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        try:
            txn = crud.get_transaction(db, transaction_id)
        except ValueError:
            return redirect("/logs", 303)
        return render_template("transaction_form.html", accounts=accounts,
                               income_categories=income_categories,
                               expense_categories=expense_categories, txn=txn,
                               error="A database constraint was violated. Check the values."), 400
    except Exception:
        accounts = crud.get_accounts(db)
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        try:
            txn = crud.get_transaction(db, transaction_id)
        except ValueError:
            return redirect("/logs", 303)
        return render_template("transaction_form.html", accounts=accounts,
                               income_categories=income_categories,
                               expense_categories=expense_categories, txn=txn,
                               error="Invalid input. Please check the form values."), 400
    try: crud.backfill_daily_profit_logs(db)
    except Exception as e: print(f"backfill error: {e}")
    return redirect("/logs", 303)


@bp.route("/<int:transaction_id>/delete", methods=["POST"])
def delete_transaction(transaction_id):
    """Delete (undo) a transaction. Reverses the balance change.

    For transfers, also deletes the paired transaction.
    For debt/receivable-linked transactions, reverts the linked record status.
    """
    db = get_db()
    try:
        crud.delete_transaction(db, transaction_id)
    except ValueError as e:
        return redirect(f"/logs?error={quote(str(e))}", 303)
    try: crud.backfill_daily_profit_logs(db)
    except Exception as e: print(f"backfill error: {e}")
    return redirect("/logs", 303)
