# AGENTS.md — CSC Shop Accounting (Flask)

## Run
```bash
conda activate accounts && python main.py
```

## Architecture
```
main.py -> routers/{accounts,categories,transactions,reports,debts,receivables}.py
        -> crud.py (all DB logic)
        -> models.py + schemas.py (dataclasses)
        -> templates/*.html (extends base.html)
```
No `__init__.py` package init — blueprints registered manually in `main.py` after `app` is created.

## Startup lifecycle (module-level, before `app` is created)
1. `restore_db()` — if DB corrupted (PRAGMA integrity_check fails), moves to `.corrupted` and restores from `.bak`
2. `create_tables()` — `Base.metadata.create_all` + ALTER TABLE for `category` column on `transactions`
3. `backup_db()` — copies to `.bak` + dated backup in `~/backups/` (keeps last 3)
4. `seed_data()` — seeds 12 default categories if table empty: Aadhaar, Recharge, Bill Payment, Insurance, IRCTC, Other Income (income); Rent, Electricity, Internet, Supplies, Food, Other Expense (expense)

## Session & DB
- `get_db()` from `database.py` stores session in `g.db` (lazy, first-call per request)
- `@app.teardown_request` commits on success, rolls back on error, closes
- `expire_on_commit=False` — ORM objects stay usable after commit/flush
- All DB writes via `flush()` only; teardown commits
- SQLite at `~/accounting.db` — auto-created; `Float` for money (intentional)

## Transaction types (4 — agents miss `loan`/`repayment`)
- `credit` / `loan` → balance increases
- `debit` / `repayment` → balance decreases (validated `balance >= amount`)
- Schema: `TransactionCreate.__post_init__` validates type and `amount > 0`

Profit queries filter `type.in_(["credit"])` for income and `type.in_(["debit"])` for expenses. Loan/repayment types are excluded from P&L (they are financing activities, not operating).

## Key quirks

### Jinja2 format filter
**Only** old-style `%` formatting: `{{ "%.2f"|format(value) }}` — NOT `"{:,.2f}"` (TypeError).

### Forms
All `application/x-www-form-urlencoded`, parsed via `request.form`. Never Flask-WTF or `get_json()`.

### Transfers
- `TransferCreate` schema, route `POST /transactions/transfer`
- Creates paired debit/credit with `category="Transfer"` and shared `reference="xfer:<uuid>"`
- Cannot create/edit/delete single side — `delete_transaction` removes both; edit raises ValueError

### Badge display
Template badges (index.html, logs.html) must distinguish all 4 types: CREDIT (success), LOAN (info), DEBIT (danger), REPAYMENT (warning). Common bug: only checking `credit` vs else → mislabels `loan` as DEBIT.

### Reference prefixes (reserved)
`debt:`, `receivable:`, `xfer:` — blocked in `create_transaction` / `update_transaction`. Used internally to link debt/repayment and receivable/received transactions.

### Edit transfer protection
`update_transaction` raises ValueError for any transaction with `category=="Transfer"` and `reference` starting with `xfer:`.

### Debt workflow (2 sides)
- **Receive loan**: `GET/POST /debts/<id>/receive` — creates `loan` transaction (credits account), sets reference `debt:<id>`. Template: `debt_receive.html`.
- **Settle debt**: `GET/POST /debts/<id>/settle` — creates `repayment` transaction (debits account), marks debt paid. Template: `debt_settle.html`.

Deleting a repayment/credit reverses debt status to "unpaid" and clears `settled_at`/`received_at`.

### Daily profit log
- Formula: `profit = income - expenses` (receivable/capital changes stored as informational columns only)
- Entry is **not** created for days with zero activity (no transactions, no receivable changes, no capital delta)
- `backfill_daily_profit_logs()` iterates from first transaction date to today

### Profit model (dashboard)
`dashboard_profit = total_balance - fixed_capital` — `fixed_capital` stored in `settings` table key-value via `Setting` model. Edit at `POST /settings/capital`.

### `type` query param
Logs route (`/logs`) uses `txn_type` as Python var but `type` as URL param: `txn_type = request.args.get("type")`.

## Error handling
- `crud.py` raises `ValueError` for business logic (insufficient balance, not found, blocked delete)
- Routes catch `ValueError` + `IntegrityError` (duplicate name/constraint violations) before generic `Exception`
- Session rollback automatic via `teardown_request` on exception
- `crud.backfill_daily_profit_logs(db)` called after most writes; failure silently ignored (`except Exception: pass`)

## Routes that exist (no missing ones)
- `/debts/<id>/receive` — loan receipt (new, agents might miss)
- `/receivables/` + `/receivables/<id>/receive` — receivable management
- `/reports/` + `/reports/profits` — P&L reports + daily profit log
- `/settings/capital` — fixed capital edit
- `/backup` — DB download

## Deployment
- WSGI only: `gunicorn main:app` or `python main.py`
- No ASGI adapter
- No test framework
