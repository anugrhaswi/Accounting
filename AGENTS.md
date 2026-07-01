# AGENTS.md — CSC Shop Accounting

## Stack & Setup
- **FastAPI** (async) + **SQLAlchemy 2.0** (async) + **aiosqlite**
- **Jinja2** templates + **Bootstrap 5** (CDN)
- Conda env `accounts` (Python 3.12)
- Run: `conda activate accounts && uvicorn main:app --reload`

## Architecture
```
main.py -> routers/{accounts,categories,transactions,reports}.py
        -> crud.py (all DB logic)
        -> models.py (Account, Transaction, Category, Setting)
        -> schemas.py (Pydantic: AccountCreate, TransactionCreate, TransferCreate, CategoryCreate)
        -> templating.py (Jinja2Templates singleton)
        -> templates/*.html (extends base.html)
```

## Must-know quirks (agents WILL miss these)

### TemplateResponse signature
Starlette 1.3.1+ uses `(request, name, context)`, NOT `(name, context)`.
Correct: `templates.TemplateResponse(request, "index.html", {...})`

### Jinja2 format filter
Uses old-style `%` formatting only.
Correct: `{{ "%.2f"|format(value) }}`
Wrong: `{{ "{:,.2f}"|format(value) }}` — TypeError

### Forms
All forms POST as `application/x-www-form-urlencoded`. Routes parse via `await request.form()` then construct Pydantic models manually — never use FastAPI `Form()` injections.

### Profit model
`net_profit = sum(all account balances) - fixed_capital`
Fixed capital stored in `settings` table as key-value via `Setting` model. Edit at `POST /settings/capital`.

## Conventions
- Routes render HTML via Jinja2 (no JSON APIs)
- POST handlers redirect with `status_code=303`
- All DB writes via `flush()` — auto-committed by `get_db` dependency's `session.begin()`
- `expire_on_commit=False` in sessionmaker — ORM objects usable after commit
- Use `selectinload` for relationship loading
- No test framework configured

## DB & data safety
- SQLite at `./accounting.db` — auto-created + auto-migrated on startup (lifespan in `main.py` runs `create_all` then `ALTER TABLE` to add `category`)
- Balance is `Float` (not Decimal) — intentional
- **CRITICAL**: Never delete `accounting.db` without asking
- `.gitignore` excludes `accounting.db`, `__pycache__/`, `*.pyc`, `.vscode/`

## Validation rules
- Account delete blocked (HTTPException 400) if transactions exist
- Both debit and transfer validate `balance >= amount` — insufficient balance returns 400
- Transaction type is `"credit"`/`"debit"` (validated via Pydantic regex)
- `amount` must be > 0 on all schemas
- Fixed capital input validated as numeric before storing
- Transfer transactions set `category="Transfer"` automatically
