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
No `__init__.py` — blueprints registered manually in `main.py` after `app` is created.

## Startup lifecycle (module-level, before `app`)
1. `restore_db()` — if PRAGMA integrity_check fails, moves to `.corrupted`, restores from `.bak`
2. `create_tables()` — `Base.metadata.create_all` + ALTER TABLE for legacy columns (`category` on `transactions`; `daily_profit_log` columns; `received_at` on `debts`). **Safe to re-run every startup.** ALTER TABLE `DEFAULT 0` does NOT backfill NULLs — explicit `UPDATE ... SET col=0 WHERE col IS NULL` follows each column addition.
3. `backup_db()` — copies to `.bak` + dated backup in `~/backups/` (keeps last 3). Wrapped in try/except.
4. `seed_data()` — seeds 12 default income/expense categories if table empty

## Session & DB
- `get_db()` stores session in `g.db` (lazy, first-call per request)
- `@app.teardown_request` commits on success, rolls back on error, closes
- `expire_on_commit=False` — ORM objects stay usable after commit/flush; BUT `account.balance` is NOT auto-refreshed. If accounts are fetched before a modifying transaction, `db.refresh(account)` is needed.
- **All DB writes via `flush()` only; teardown commits.** Do NOT call `db.commit()` manually.
- SQLite at `~/accounting.db`; `Float` for money (intentional)

## Transaction types (4)
- `credit` / `loan` → balance increases
- `debit` / `repayment` → balance decreases (validated `balance >= amount`)
- `TransactionCreate.__post_init__` validates `type`, `amount > 0`, `account_id > 0`
- P&L queries filter `type.in_("credit")` for income, `type.in_("debit")` for expenses. `loan`/`repayment` are financing activities, excluded from P&L.

## Key quirks

### Jinja2 format filter
**Only** old-style `%` formatting: `{{ "%.2f"|format(value) }}` — NOT `"{:,.2f}"` (TypeError).

### Forms
All `application/x-www-form-urlencoded` via `request.form`. Never Flask-WTF or `get_json()`.

### Templates: avoid Jinja tags in HTML comments
`<!-- {% ... %} -->` is parsed by Jinja. Use `{# ... #}` instead.

### Transfers
- `TransferCreate` validates `from_account_id != to_account_id`
- `POST /transactions/transfer` creates paired debit/credit with `category="Transfer"` and shared `reference="xfer:<uuid>"`
- Cannot create/edit/delete single side — `delete_transaction` removes both; `update_transaction` blocks edits via `category == "Transfer"` check

### Reference prefixes (reserved)
`debt:`, `receivable:`, `xfer:` — blocked in `create_transaction`/`update_transaction` for user-submitted references. Used internally to link related transactions.

### Debt workflow (loans only)
- **Receive loan**: `GET/POST /debts/<id>/receive` — creates `loan` transaction (credits account), sets `reference="debt:<id>"`
- **Settle debt**: `GET/POST /debts/<id>/settle` — creates `repayment` transaction (debits account), marks debt paid
- Template shows **Receive** when `received_at` is null, **Pay** when `received_at` is set (never both)
- Deleting a `repayment` TXN reverts debt to unpaid. Deleting a `loan` TXN when debt is paid is blocked (must delete repayment first).

### Receivable workflow
- `GET/POST /receivables/<id>/receive` — creates `credit` transaction, sets `reference="receivable:<id>"`
- Deleting the linked `credit` TXN reverts receivable to unreceived

### Daily profit log (manual)
- No automated calculation. User logs profit via `POST /daily-profit/log` (accepts `date` + `profit`).
- `crud.log_daily_profit(log_date, profit)` creates or updates by date.
- Dashboard Profit card has an inline "Log Profit" button with date/profit form.
- View at `/reports/profits` (shows date, profit, running total).
- `today` context processor available in all templates.

### Dashboard profit model
`dashboard_profit = total_balance - fixed_capital`. `fixed_capital` stored in `settings` table via `Setting` model. Edit at `POST /settings/capital`.

### `type` query param
Logs route (`/logs`) uses `txn_type` as Python var but `type` as URL param: `txn_type = request.args.get("type")`.

## Error handling
- `crud.py` raises `ValueError` for business logic (insufficient balance, not found, blocked delete)
- Routes catch `ValueError` + `IntegrityError` before generic `Exception`
- Session rollback automatic via `teardown_request` on exception

## Common pitfalls

### Account balance is manual
`create_transaction`, `delete_transaction`, `transfer_money`, `settle_debt`, `receive_loan`, `receive_receivable` all manually increment/decrement `account.balance`. No DB triggers or ORM events. Do not add `event.listen()`.

### `delete_transaction` extra safety
`update_transaction` uses `category == "Transfer"` as sole check. `delete_transaction` also checks `reference.startswith("xfer:")` for extra safety. Both are fine.

### `get_accounts` returns session objects
Because `expire_on_commit=False`, accounts fetched in the same request reflect flushed values. In a new request, committed values are read. Both cases correct.

## Routes
- `/debts/<id>/receive` — loan receipt
- `/receivables/` + `/receivables/<id>/receive` — receivable management
- `/reports/` + `/reports/profits` — P&L reports + manual profit log
- `/daily-profit/log` — `POST` only, manual profit entry
- `/settings/capital` — fixed capital edit
- `/backup` — DB download

## Deployment
- `python main.py` or `gunicorn main:app` (WSGI only, no ASGI adapter)
- No test framework
