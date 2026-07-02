from datetime import datetime, timezone

from flask import Flask, g, redirect, render_template, request
from sqlalchemy import text

from database import engine, Base, SessionLocal, get_db
import crud


def create_tables():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        result = conn.execute(text("PRAGMA table_info(transactions)"))
        cols = [r[1] for r in result]
        if "category" not in cols:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN category VARCHAR(50)"))


def seed_data():
    with SessionLocal() as session:
        crud.seed_default_categories(session)
        session.commit()


create_tables()
seed_data()

app = Flask(__name__)

from routers.accounts import bp as accounts_bp
from routers.categories import bp as categories_bp
from routers.transactions import bp as transactions_bp
from routers.reports import bp as reports_bp
from routers.debts import bp as debts_bp

app.register_blueprint(accounts_bp)
app.register_blueprint(categories_bp)
app.register_blueprint(transactions_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(debts_bp)


@app.teardown_request
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        if exception is None:
            db.commit()
        else:
            db.rollback()
        db.close()


@app.route("/")
def dashboard():
    db = get_db()
    error = request.args.get("error")
    accounts_list = crud.get_accounts(db)
    recent_transactions = crud.get_transactions(db, limit=10)
    summary = crud.get_daily_summary(db)
    total_balance = crud.get_total_balance(db)
    try:
        fixed_capital = float(crud.get_setting(db, "fixed_capital", "0"))
    except (ValueError, TypeError):
        fixed_capital = 0.0
    net_profit = total_balance - fixed_capital
    outstanding_debt = crud.get_total_outstanding_debt(db)
    return render_template("index.html", accounts=accounts_list, recent_transactions=recent_transactions, summary=summary, total_balance=total_balance, fixed_capital=fixed_capital, net_profit=net_profit, outstanding_debt=outstanding_debt, error=error)


@app.route("/settings/capital", methods=["POST"])
def update_capital():
    db = get_db()
    value = request.form.get("fixed_capital", "0")
    try:
        float(value)
    except (ValueError, TypeError):
        value = "0"
    crud.set_setting(db, "fixed_capital", value)
    return redirect("/", 303)


@app.route("/logs")
def view_logs():
    db = get_db()
    account_id_arg = request.args.get("account_id")
    account_id = int(account_id_arg) if account_id_arg else None
    txn_type = request.args.get("type")
    accounts = crud.get_accounts(db)
    transactions_list = crud.get_transactions(db, account_id=account_id, txn_type=txn_type, limit=200)
    return render_template("logs.html", accounts=accounts, transactions=transactions_list, selected_account_id=account_id, selected_type=txn_type)


if __name__ == "__main__":
    app.run(debug=True)
