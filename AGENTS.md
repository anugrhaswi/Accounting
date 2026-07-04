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
2. `create_tables()` — `Base.metadata.create_all` + ALTER TABLE for legacy columns (`category` in `transactions`; `daily_profit_log` columns; `received_at` in `debts`). **Safe to re-run every startup.**
3. `backup_db()` — copies to `.bak` + dated backup in `~/backups/` (keeps last 3)
4. `seed_data()` — seeds 12 default income/expense categories if table empty

## Session & DB
- `get_db()` from `database.py` stores session in `g.db` (lazy, first-call per request)
- `@app.teardown_request` commits on success, rolls back on error, closes
- `expire_on_commit=False` — ORM objects stay usable after commit/flush; however, Balance updates on Account objects are NOT automatically refreshed by the ORM. Templates referencing `account.balance` must access the session that modified it. Use `db.refresh(account)` if accounts are fetched before the transaction that modifies them.
- All DB writes via `flush()` only; teardown commits
- SQLite at `~/accounting.db` — auto-created; `Float` for money (intentional)

## Transaction types (4 — agents miss `loan`/`repayment`)
- `credit` / `loan` → balance increases
- `debit` / `repayment` → balance decreases (validated `balance >= amount`)
- Schema: `TransactionCreate.__post_init__` validates `type`, `amount > 0`, and `account_id > 0`.

Profit queries filter `type.in_("credit")` for income and `type.in_("debit")` for expenses. Loan/repayment types are excluded from P&L (they are financing activities, not operating).

## Key quirks

### Jinja2 format filter
**Only** old-style `%` formatting: `{{ "%.2f"|format(value) }}` — NOT `"{:,.2f}"` (TypeError).

### Forms
All `application/x-www-form-urlencoded`, parsed via `request.form`. Never Flask-WTF or `get_json()`.

### Transfers
- `TransferCreate.__post_init__` validates that `from_account_id != to_account_id`.
- Route `POST /transactions/transfer` creates paired debit/credit with `category="Transfer"` and shared `reference="xfer:<uuid>"`.
- Cannot create/edit/delete single side — `delete_transaction` removes both; edit raises `ValueError`.

### Edit transfer protection
`update_transaction` blocks editing any transaction where `category == "Transfer"`, regardless of `reference` prefix. Previously relied on `reference.startswith("xfer:")`; this was brittle. The `Transfer` category itself is the canonical indicator.

### Reference prefixes (reserved)
`debt:`, `receivable:`, `xfer:` — blocked in `create_transaction` / `update_transaction`. Used internally to link debt/repayment and receivable/received transactions.

### Debt workflow (2 sides)
- **Receive loan**: `GET/POST /debts/<id>/receive` — creates `loan` transaction (credits account), sets reference `debt:<id>`. Template: `debt_receive.html`.
- **Settle debt**: `GET/POST /debts/<id>/settle` — creates `repayment` transaction (debits account), marks debt paid. Template: `debt_settle.html`.

**Important:** `settle_debt()` does NOT require `received_at` to be set. This is intentional — debts double as bill/obligation tracking (e.g. electricity bill created as a debt, paid directly without money ever entering an account). `receive_loan()` already blocks receiving after settlement (`status == "paid"`), so the inconsistency is contained.

Deleting a repayment/credit reverses debt status to "unpaid" and clears `settled_at`/`received_at`.
- Deleting a `loan` TXN when `debt.status == "paid"` is blocked — the repayment TXN must be deleted first.

### Daily profit log
- Formula: `profit = income - expenses` (receivable/capital changes stored as informational columns only)
- Entry is **not** created for days with zero activity (no transactions, no receivable changes, no capital delta)
- `backfill_daily_profit_logs()` iterates from first transaction date to today
- **Pitfall:** `backfill_daily_profit_logs` only calls `db.flush()`. It relies on the request `teardown_request` to commit. Do **not** add `db.commit()` inside it—this would break the single-transaction-per-request architecture.
- **Pitfall (fixed):** The original `backfill_daily_profit_logs` only went forward from `last_log + 1 day`, so historical edits/deletions left stale entries. It now always recalculates from the first transaction date to today to keep logs accurate.

### `daily_profit_log` migration and NULL defaults
When `create_tables()` runs `ALTER TABLE daily_profit_log ADD COLUMN ... DEFAULT 0`, SQLite does **not** backfill existing rows with `0`--they remain `NULL`. Because the model declares `nullable=False`, reading old rows causes `TypeError` when the template tries `"%.2f"|format(None)`. The fix: run `UPDATE daily_profit_log SET col = 0 WHERE col IS NULL` after each `ALTER TABLE ADD COLUMN`.

### Profit model (dashboard)
`dashboard_profit = total_balance - fixed_capital` -- `fixed_capit:` stored in `settings` table key-value via `Setting` model. Edit at `POST /settings/capital`.

### `type` query param
Logs route (`/logs`) uses `txn_type` as Python var but `type` as URL param: `txn_type = request.args.get("type")`.

### Receivable workflow
`GET/POST /receivables/<id>/receive`: creates a standard `credit` transaction (links via `receivable:<id>` reference).
- Deleting a `receivable` TXN only works if the receivable is still "unreceived".
- Deleting the linked `credit` TXN reverts the receivable to "unreceived" and clears `received_at`.

## Error handling
- `crud.py` raises `ValueError` for business logic (insufficient balance, not found, blocked delete). `update_account` also validates name uniqueness preemptively via a query before any `flush`, yielding cleaner error messages than raw `IntegrityError`.
- Routes catch `ValueError` + `IntegrityError` (duplicate name/constraint violations) before generic `Exception`.
- Session rollback automatic via `teardown_request` on exception.
- `crud.backfill_daily_profit_logs(db)` called after most writes; failure silently ignored (`except Exception: pass`).

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

## Common False Positives (things that look like bugs but are not)

### Account balance is updated manually, not via SQL triggers or ORM events
In `crud.py`, `create_transaction`, `delete_transaction`, `transfer_money`, `settle_debt`, `receive_loan`, and `receive_receivable` all manually increment/decrement `account.balance`. There is no DB-level trigger. This is by design -- the single-transaction-per-request architecture guarantees atomicity via `flush()` + `teardown_request` commit. Do not add SQLAlchemy `event.listen()` or DB triggers.

### `loan` and `repayment` are excluded from P&L by design
`get_daily_summary`, `update_daily_profit_log`, and the monthly reports all filter `type.in_(["credit"])` for income and `type.in_(["debit"])` for expenses. `loan` and `repayment` are financing activities, not operating P&L. This is intentional.

### `delete_transaction` uses both `category == "Transfer"` and `reference.startswith("xfer:")`
`update_transaction` uses `category == "Transfer"` as the sole check (the canonical indicator). `delete_transaction` still checks both for extra safety. This is fine -- it does not hurt correctness.

### `settle_debt` does not check `received_at`
A debt can be settled directly without ever having received the loan (bill/obligation tracking). The `received_at` field is only set if `receive_loan()` was called. This is intentional -- `receive_loan` is blocked once a debt is paid.

### `get_accounts` fetches all accounts from the current session
Because `expire_on_commit=False`, if `get_accounts` is called in the same request after a balance change, the returned objects reflect the latest flushed values. If called in a later request (new session), the committed values are read. Both cases are correct.

## Historical audit notes (2026-07-04)
Audit found 3 real bugs and 2 polish items:
1. `daily_profit_log` migration left `NULL` values in existing rows after `ALTER TABLE ADD COLUMN` -- fixed by backfilling `NULL`s to `0`.
2. `backfill_daily_profit_logs` was forward-only and did not re-compute past days -- fixed to always iterate from first transaction date to today.
3. `update_transaction` allowed changing `account_id` on debt/receivable-linked transactions -- fixed to block it.
4. `backup_db` could crash startup on disk errors -- wrapped in try/except.
5. Delete buttons shown for non-deletable items (paid debts, received receivables) -- templates conditionally hide them.
