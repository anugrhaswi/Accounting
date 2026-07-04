"""Receivable management routes (CRUD at /receivables/...) plus receive payment.

Receivable lifecycle: create (unreceived) → receive payment into an account (received).
"""

import math
from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request
from sqlalchemy.exc import IntegrityError
from database import get_db
import crud
import schemas

bp = Blueprint("receivables", __name__, url_prefix="/receivables")


@bp.route("/")
def list_receivables():
    """Show the receivables list page with optional status filter and outstanding total."""
    db = get_db()
    error = request.args.get("error")
    status = request.args.get("status")
    receivables = crud.get_receivables(db, status=status)
    outstanding = crud.get_total_outstanding_receivable(db)
    return render_template("receivables.html", receivables=receivables,
                           outstanding=outstanding, selected_status=status, error=error)


@bp.route("/", methods=["POST"])
def create_receivable():
    """Handle receivable creation from form submission."""
    db = get_db()
    form = request.form
    try:
        amount = float(form["amount"])
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
        data = schemas.ReceivableCreate(
            debtor=form["debtor"].strip(),
            amount=amount,
            category=(form.get("category") or "").strip() or "General",
            description=(form.get("description") or "").strip() or None,
            due_date=(form.get("due_date") or "").strip() or None,
        )
        crud.create_receivable(db, data)
    except (ValueError, TypeError) as e:
        receivables = crud.get_receivables(db)
        outstanding = crud.get_total_outstanding_receivable(db)
        form_values = {"debtor": form.get("debtor", ""), "amount": form.get("amount", ""),
                       "category": form.get("category", ""), "description": form.get("description", ""),
                       "due_date": form.get("due_date", "")}
        return render_template("receivables.html", receivables=receivables,
                               outstanding=outstanding, error=str(e), form_values=form_values), 400
    except IntegrityError:
        receivables = crud.get_receivables(db)
        outstanding = crud.get_total_outstanding_receivable(db)
        form_values = {"debtor": form.get("debtor", ""), "amount": form.get("amount", ""),
                       "category": form.get("category", ""), "description": form.get("description", ""),
                       "due_date": form.get("due_date", "")}
        return render_template("receivables.html", receivables=receivables,
                               outstanding=outstanding,
                               error="A database constraint was violated. Check the values.", form_values=form_values), 400
    except Exception:
        receivables = crud.get_receivables(db)
        outstanding = crud.get_total_outstanding_receivable(db)
        form_values = {"debtor": form.get("debtor", ""), "amount": form.get("amount", ""),
                       "category": form.get("category", ""), "description": form.get("description", ""),
                       "due_date": form.get("due_date", "")}
        return render_template("receivables.html", receivables=receivables,
                               outstanding=outstanding,
                               error="Invalid input. Please check the form values.", form_values=form_values), 400
    return redirect("/receivables/", 303)


@bp.route("/<int:recv_id>/receive")
def receive_form(recv_id):
    """Show the form to receive a receivable payment into an account."""
    db = get_db()
    try:
        recv = crud.get_receivable(db, recv_id)
    except ValueError:
        return redirect("/receivables/", 303)
    if recv.status == "received":
        return redirect("/receivables/", 303)
    accounts = crud.get_accounts(db)
    return render_template("receivable_receive.html", recv=recv, accounts=accounts)


@bp.route("/<int:recv_id>/receive", methods=["POST"])
def receive_receivable(recv_id):
    """Handle receivable payment receipt into a selected account."""
    db = get_db()
    try:
        account_id = int(request.form["account_id"])
    except (ValueError, TypeError):
        try:
            recv = crud.get_receivable(db, recv_id)
            accounts = crud.get_accounts(db)
        except ValueError:
            return redirect("/receivables/", 303)
        return render_template("receivable_receive.html", recv=recv,
                               accounts=accounts, error="Invalid numeric value."), 400
    try:
        crud.receive_receivable(db, recv_id, account_id)
    except (ValueError, KeyError) as e:
        try:
            recv = crud.get_receivable(db, recv_id)
            accounts = crud.get_accounts(db)
        except ValueError:
            return redirect("/receivables/", 303)
        return render_template("receivable_receive.html", recv=recv,
                               accounts=accounts, error=str(e)), 400
    return redirect("/receivables/", 303)


@bp.route("/<int:recv_id>/edit")
def edit_receivable_form(recv_id):
    """Show the receivable edit form pre-filled with existing data."""
    db = get_db()
    try:
        recv = crud.get_receivable(db, recv_id)
    except ValueError:
        return redirect("/receivables/", 303)
    return render_template("receivable_edit.html", recv=recv)


@bp.route("/<int:recv_id>/edit", methods=["POST"])
def edit_receivable(recv_id):
    """Handle receivable update from form submission.

    For received receivables: only metadata (debtor, category, description) may change.
    """
    db = get_db()
    form = request.form
    try:
        data = schemas.ReceivableCreate(
            debtor=form["debtor"].strip(),
            amount=float(form["amount"]),
            category=(form.get("category") or "").strip() or "General",
            description=(form.get("description") or "").strip() or None,
            due_date=(form.get("due_date") or "").strip() or None,
        )
        crud.update_receivable(db, recv_id, data)
    except ValueError as e:
        try:
            recv = crud.get_receivable(db, recv_id)
        except ValueError:
            return redirect("/receivables/", 303)
        return render_template("receivable_edit.html", recv=recv, error=str(e)), 400
    except IntegrityError:
        try:
            recv = crud.get_receivable(db, recv_id)
        except ValueError:
            return redirect("/receivables/", 303)
        return render_template("receivable_edit.html", recv=recv, error="A database constraint was violated. Check the values."), 400
    except Exception:
        try:
            recv = crud.get_receivable(db, recv_id)
        except ValueError:
            return redirect("/receivables/", 303)
        return render_template("receivable_edit.html", recv=recv, error="Invalid input. Please check the form values."), 400
    return redirect("/receivables/", 303)


@bp.route("/<int:recv_id>/delete", methods=["POST"])
def delete_receivable(recv_id):
    """Delete an unreceived receivable. Received receivables cannot be deleted."""
    db = get_db()
    try:
        crud.delete_receivable(db, recv_id)
    except ValueError as e:
        return redirect(f"/receivables/?error={quote(str(e))}", 303)
    return redirect("/receivables/", 303)
