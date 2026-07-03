import os
import shutil
from datetime import date, datetime, timezone

from flask import Flask, g, redirect, render_template, request, send_file
from sqlalchemy import text

from database import engine, Base, SessionLocal, get_db, DB_PATH
import crud

BACKUP_DIR = os.path.join(os.path.expanduser("~"), "backups")
BAK_PATH = DB_PATH + ".bak"


def restore_db():
    if not os.path.exists(DB_PATH) and os.path.exists(BAK_PATH):
        shutil.copy2(BAK_PATH, DB_PATH)


def backup_db():
    if os.path.exists(DB_PATH):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        dated = os.path.join(BACKUP_DIR, f"accounting_{date.today()}.db")
        shutil.copy2(DB_PATH, dated)
        shutil.copy2(DB_PATH, BAK_PATH)
        backups = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("accounting_"))
        for old in backups[:-3]:
            os.remove(os.path.join(BACKUP_DIR, old))


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


restore_db()
create_tables()
backup_db()
seed_data()

app = Flask(__name__)

from routers.accounts import bp as accounts_bp
from routers.categories import bp as categories_bp
from routers.transactions import bp as transactions_bp
from routers.reports import bp as reports_bp
from routers.debts import bp as debts_bp
from routers.receivables import bp as receivables_bp

app.register_blueprint(accounts_bp)
app.register_blueprint(categories_bp)
app.register_blueprint(transactions_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(debts_bp)
app.register_blueprint(receivables_bp)

@app.teardown_request
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            if exception is None:
                db.commit()
            else:
                db.rollback()
        finally:
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
    profit = total_balance - fixed_capital
    outstanding_debt = crud.get_total_outstanding_debt(db)
    net_profit = profit - outstanding_debt
    outstanding_receivable = crud.get_total_outstanding_receivable(db)
    net_worth = total_balance + outstanding_receivable - outstanding_debt
    return render_template("index.html", accounts=accounts_list, recent_transactions=recent_transactions, summary=summary, total_balance=total_balance, fixed_capital=fixed_capital, profit=profit, net_profit=net_profit, outstanding_debt=outstanding_debt, outstanding_receivable=outstanding_receivable, net_worth=net_worth, error=error)


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
    error = request.args.get("error")
    account_id_arg = request.args.get("account_id")
    try:
        account_id = int(account_id_arg) if account_id_arg else None
    except (ValueError, TypeError):
        account_id = None
    txn_type = request.args.get("type")
    accounts = crud.get_accounts(db)
    transactions_list = crud.get_transactions(db, account_id=account_id, txn_type=txn_type, limit=200)
    return render_template("logs.html", accounts=accounts, transactions=transactions_list, selected_account_id=account_id, selected_type=txn_type, error=error)


@app.route("/backup")
def download_backup():
    return send_file(DB_PATH, as_attachment=True, download_name="accounting_backup.db")


if __name__ == "__main__":
    app.run()
