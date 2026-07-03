from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request
from database import get_db
import crud
import schemas

bp = Blueprint("receivables", __name__, url_prefix="/receivables")


@bp.route("/")
def list_receivables():
    db = get_db()
    error = request.args.get("error")
    status = request.args.get("status")
    receivables = crud.get_receivables(db, status=status)
    outstanding = crud.get_total_outstanding_receivable(db)
    return render_template("receivables.html", receivables=receivables,
                           outstanding=outstanding, selected_status=status, error=error)


@bp.route("/", methods=["POST"])
def create_receivable():
    db = get_db()
    form = request.form
    try:
        data = schemas.ReceivableCreate(
            debtor=form["debtor"],
            amount=float(form["amount"]),
            category=form.get("category") or "General",
            description=form.get("description") or None,
            due_date=form.get("due_date") or None,
        )
        crud.create_receivable(db, data)
    except Exception:
        receivables = crud.get_receivables(db)
        outstanding = crud.get_total_outstanding_receivable(db)
        return render_template("receivables.html", receivables=receivables,
                               outstanding=outstanding,
                               error="Invalid input. Please check the form values."), 400
    return redirect("/receivables/", 303)


@bp.route("/<int:recv_id>/receive")
def receive_form(recv_id):
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
    db = get_db()
    try:
        account_id = int(request.form["account_id"])
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
    db = get_db()
    try:
        recv = crud.get_receivable(db, recv_id)
    except ValueError:
        return redirect("/receivables/", 303)
    return render_template("receivable_edit.html", recv=recv)


@bp.route("/<int:recv_id>/edit", methods=["POST"])
def edit_receivable(recv_id):
    db = get_db()
    form = request.form
    try:
        data = schemas.ReceivableCreate(
            debtor=form["debtor"],
            amount=float(form["amount"]),
            category=form.get("category") or "General",
            description=form.get("description") or None,
            due_date=form.get("due_date") or None,
        )
        crud.update_receivable(db, recv_id, data)
    except Exception:
        try:
            recv = crud.get_receivable(db, recv_id)
        except ValueError:
            return redirect("/receivables/", 303)
        return render_template("receivable_edit.html", recv=recv, error="Invalid input. Please check the form values."), 400
    return redirect("/receivables/", 303)


@bp.route("/<int:recv_id>/delete", methods=["POST"])
def delete_receivable(recv_id):
    db = get_db()
    try:
        crud.delete_receivable(db, recv_id)
    except ValueError as e:
        return redirect(f"/receivables/?error={quote(str(e))}", 303)
    return redirect("/receivables/", 303)
