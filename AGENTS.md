# AGENTS.md — CSC Shop Accounting (Flask)

## Stack & Setup
- **Flask 3.x** (sync) + **SQLAlchemy 2.0** (sync) + **SQLite**
- **Jinja2** (Flask built-in) + **Bootstrap 5** (CDN)
- Conda env `accounts` (Python 3.12)
- Run: `conda activate accounts && python main.py`

## Architecture
```
main.py -> routers/{accounts,categories,transactions,reports,debts}.py
        -> crud.py (all DB logic)
        -> models.py (Account, Transaction, Category, Setting, Debt)
        -> schemas.py (dataclasses: AccountCreate, TransactionCreate, TransferCreate, CategoryCreate, DebtCreate)
        -> templates/*.html (extends base.html)
```

## Session management
- DB session stored in `g.db` via `get_db()` from `database.py`
- `get_db()` creates session lazily on first call in each request
- `@app.teardown_request` auto-commits on success, rolls back on error, then closes
- Startup: `create_tables()` runs `Base.metadata.create_all` + ALTER TABLE; `seed_data()` seeds 12 default categories — both at module level before `app` is created

## Must-know quirks (agents WILL miss these)

### TemplateResponse → render_template
Flask uses `render_template("index.html", ...)` — NOT `templates.TemplateResponse(request, ...)`.

### Jinja2 format filter
Uses old-style `%` formatting only.
Correct: `{{ "%.2f"|format(value) }}`
Wrong: `{{ "{:,.2f}"|format(value) }}` — TypeError

### Forms
All forms POST as `application/x-www-form-urlencoded`. Routes parse via `request.form` (synchronous `MultiDict`). Never use Flask-WTF or `flask.request.get_json()`.

### Profit model
`net_profit = sum(all account balances) - fixed_capital`
Fixed capital stored in `settings` table as key-value via `Setting` model. Edit at `POST /settings/capital`.

### `type` query param
Logs route uses `txn_type` as the Python variable but `type` as the URL query param:
`txn_type = request.args.get("type")`
Template `<select name="type">` matches the URL param.

## Conventions
- Routes render HTML via Jinja2 (no JSON APIs)
- POST handlers redirect with `303` status via `redirect(url, 303)`
- All DB writes via `flush()` — auto-committed by `teardown_request`
- `expire_on_commit=False` in sessionmaker — ORM objects usable after commit
- Use `selectinload` for relationship loading
- No test framework configured

## DB & data safety
- SQLite at `./accounting.db` — auto-created + auto-migrated on startup
- Balance is `Float` (not Decimal) — intentional
- **CRITICAL**: Never delete `accounting.db` without asking
- `.gitignore` excludes `accounting.db`, `__pycache__/`, `*.pyc`, `.vscode/`

## Startup lifecycle
1. `create_tables()` runs synchronously at module level: `Base.metadata.create_all` + ALTER TABLE to add `category` column
2. `seed_data()` runs next: opens a separate `SessionLocal()` to seed 12 default categories if table is empty
3. Flask app is created, blueprints registered
- Categories seeded: Aadhaar, Recharge, Bill Payment, Insurance, IRCTC, Other Income (income); Rent, Electricity, Internet, Supplies, Food, Other Expense (expense).

## Validation rules
- Account delete blocked (`ValueError`) if transactions exist
- Both debit and transfer validate `balance >= amount` — insufficient balance returns 400
- Transaction type is `"credit"`/`"debit"` (validated via `TransactionCreate.__post_init__`)
- `amount` must be > 0 on all schemas (validated via `__post_init__`)
- Fixed capital input validated as numeric before storing
- Transfer transactions set `category="Transfer"` automatically

## Error handling
- `crud.py` raises `ValueError` for business logic errors (insufficient balance, not found)
- Routes catch `ValueError` to re-render forms with error messages
- Generic `Exception` catch for unexpected errors (e.g. duplicate name, invalid form values)
- Session rollback handled automatically by `teardown_request` when exceptions propagate

## Deployment
- **WSGI only** — standard Flask app. Deploy via `gunicorn main:app` or `python main.py`.
- Cannot run on ASGI-only hosts without a WSGI adapter.
