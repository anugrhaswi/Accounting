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


@bp.route("/<int:account_id>/delete", methods=["POST"])
def delete_account(account_id):
    db = get_db()
    try:
        crud.delete_account(db, account_id)
    except ValueError as e:
        return redirect(f"/?error={quote(str(e))}", 303)
    return redirect("/", 303)
