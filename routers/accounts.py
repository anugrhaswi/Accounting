from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request
from database import get_db
import crud
import schemas

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/new")
def new_account_form():
    return render_template("account_form.html")


@bp.route("/", methods=["POST"])
def create_account():
    db = get_db()
    form = request.form
    data = schemas.AccountCreate(
        name=form["name"],
        type=form.get("type", "General"),
        description=form.get("description") or None,
    )
    try:
        crud.create_account(db, data)
    except Exception:
        return render_template("account_form.html", error="Failed to create account. Please check the values."), 400
    return redirect("/", 303)


@bp.route("/<int:account_id>/edit")
def edit_account_form(account_id):
    db = get_db()
    try:
        account = crud.get_account(db, account_id)
    except ValueError:
        return redirect("/", 303)
    return render_template("account_form.html", account=account)


@bp.route("/<int:account_id>/edit", methods=["POST"])
def edit_account(account_id):
    db = get_db()
    form = request.form
    try:
        data = schemas.AccountCreate(
            name=form["name"],
            type=form.get("type", "General"),
            description=form.get("description") or None,
        )
        crud.update_account(db, account_id, data)
    except Exception:
        try:
            account = crud.get_account(db, account_id)
        except ValueError:
            return redirect("/", 303)
        return render_template("account_form.html", account=account, error="Failed to update account. Please check the values."), 400
    return redirect("/", 303)


@bp.route("/<int:account_id>/delete", methods=["POST"])
def delete_account(account_id):
    db = get_db()
    try:
        crud.delete_account(db, account_id)
    except ValueError as e:
        return redirect(f"/?error={quote(str(e))}", 303)
    return redirect("/", 303)
