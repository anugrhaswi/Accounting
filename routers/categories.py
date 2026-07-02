from urllib.parse import quote

from flask import Blueprint, redirect, render_template, request
from database import get_db
import crud
import schemas

bp = Blueprint("categories", __name__, url_prefix="/categories")


@bp.route("/")
def list_categories():
    db = get_db()
    error = request.args.get("error")
    income_categories = crud.get_categories(db, cat_type="income")
    expense_categories = crud.get_categories(db, cat_type="expense")
    return render_template("categories.html", income_categories=income_categories, expense_categories=expense_categories, error=error)


@bp.route("/", methods=["POST"])
def create_category():
    db = get_db()
    form = request.form
    try:
        data = schemas.CategoryCreate(
            name=form["name"],
            type=form["type"],
        )
        crud.create_category(db, data)
    except Exception:
        income_categories = crud.get_categories(db, cat_type="income")
        expense_categories = crud.get_categories(db, cat_type="expense")
        return render_template("categories.html", income_categories=income_categories, expense_categories=expense_categories, error="A category with this name already exists."), 400
    return redirect("/categories/", 303)


@bp.route("/<int:category_id>/delete", methods=["POST"])
def delete_category(category_id):
    db = get_db()
    try:
        crud.delete_category(db, category_id)
    except ValueError as e:
        return redirect(f"/categories/?error={quote(str(e))}", 303)
    return redirect("/categories/", 303)
