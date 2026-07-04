"""Flask application entry point with startup lifecycle.

Startup order (module-level, before app is created):
  1. restore_db()  — recover from corruption using .bak
  2. create_tables() — ensure all tables and schema migrations exist
  3. backup_db()   — create dated backup + .bak
  4. seed_data()   — populate default categories if empty

Blueprints are registered manually after app creation (no __init__ package).
"""

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
    """Check DB integrity on startup. If corrupted, restore from .bak backup."""
    if os.path.exists(DB_PATH):
        try:
            with engine.connect() as conn:
                result = conn.execute(text("PRAGMA integrity_check")).scalar()
                if result != "ok":
                    raise RuntimeError(f"DB integrity check failed: {result}")
        except Exception:
            corrupted = DB_PATH + ".corrupted"
            shutil.move(DB_PATH, corrupted)
            print(f"DB corrupted — moved to {corrupted}")
    if not os.path.exists(DB_PATH) and os.path.exists(BAK_PATH):
        shutil.copy2(BAK_PATH, DB_PATH)


def backup_db():
    """Copy current DB to .bak and a dated backup file. Keeps the 3 most recent dated backups."""
    if os.path.exists(DB_PATH):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        dated = os.path.join(BACKUP_DIR, f"accounting_{date.today()}.db")
        shutil.copy2(DB_PATH, dated)
        shutil.copy2(DB_PATH, BAK_PATH)
        backups = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("accounting_"))
        for old in backups[:-3]:
            os.remove(os.path.join(BACKUP_DIR, old))


def create_tables():
    """Create all tables via SQLAlchemy and run ALTER TABLE migrations for legacy columns."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        result = conn.execute(text("PRAGMA table_info(transactions)"))
        cols = [r[1] for r in result]
        if "category" not in cols:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN category VARCHAR(50)"))

        result = conn.execute(text("PRAGMA table_info(daily_profit_log)"))
        cols = [r[1] for r in result]
        for col in ["new_receivables", "received_receivables", "capital", "capital_delta"]:
            if col not in cols:
                conn.execute(text(f"ALTER TABLE daily_profit_log ADD COLUMN {col} FLOAT DEFAULT 0"))
                conn.execute(text(f"UPDATE daily_profit_log SET {col} = 0 WHERE {col} IS NULL"))

        result = conn.execute(text("PRAGMA table_info(debts)"))
        cols = [r[1] for r in result]
        if "received_at" not in cols:
            conn.execute(text("ALTER TABLE debts ADD COLUMN received_at DATETIME"))


def seed_data():
    """Seed default income/expense categories if the categories table is empty."""
    with SessionLocal() as session:
        crud.seed_default_categories(session)
        session.commit()


restore_db()
create_tables()
try:
    backup_db()
except Exception as e:
    print(f"Backup failed: {e}")
try:
    seed_data()
except Exception as e:
    print(f"Seed failed: {e}")

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
    """Commit or roll back the session at the end of each request."""
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
    """Render the main dashboard with account balances, recent transactions, and P&L summary."""
    db = get_db()
    error = request.args.get("error")
    accounts_list = crud.get_accounts(db)
    recent_transactions = crud.get_transactions(db, limit=10)
    total_balance = crud.get_total_balance(db)
    try:
        fixed_capital = float(crud.get_setting(db, "fixed_capital", "0"))
    except (ValueError, TypeError):
        fixed_capital = 0.0
    profit = total_balance - fixed_capital
    outstanding_debt = crud.get_total_outstanding_debt(db)
    outstanding_receivable = crud.get_total_outstanding_receivable(db)
    net_worth = total_balance + outstanding_receivable - outstanding_debt
    return render_template("index.html", accounts=accounts_list, recent_transactions=recent_transactions, total_balance=total_balance, fixed_capital=fixed_capital, profit=profit, outstanding_debt=outstanding_debt, outstanding_receivable=outstanding_receivable, net_worth=net_worth, error=error)


@app.route("/settings/capital", methods=["POST"])
def update_capital():
    """Update the fixed capital setting and backfill daily profit logs."""
    db = get_db()
    value = request.form.get("fixed_capital", "0")
    try:
        float(value)
    except (ValueError, TypeError):
        value = "0"
    crud.set_setting(db, "fixed_capital", value)
    return redirect("/", 303)


@app.context_processor
def inject_today():
    """Make today's date available in all templates."""
    return {"today": datetime.now(timezone.utc)}


@app.route("/daily-profit/log", methods=["POST"])
def log_daily_profit():
    """Manually log today's profit. Accepts date (defaults to today) and profit amount."""
    db = get_db()
    try:
        profit = float(request.form.get("profit", 0))
    except (ValueError, TypeError):
        return redirect("/?error=Invalid profit value", 303)
    date_str = request.form.get("date", "")
    try:
        if date_str:
            log_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            log_date = datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        return redirect("/?error=Invalid date format", 303)
    crud.log_daily_profit(db, log_date, profit)
    return redirect("/", 303)


@app.route("/logs")
def view_logs():
    """Render the transaction log viewer with optional account/type filters."""
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
    """Download the current SQLite database file as an attachment."""
    return send_file(DB_PATH, as_attachment=True, download_name="accounting_backup.db")


if __name__ == "__main__":
    app.run()
