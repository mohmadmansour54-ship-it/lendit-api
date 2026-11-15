# LendIt API

![CI](https://github.com/mohmadmansour54-ship-it/lendit-api/actions/workflows/ci.yml/badge.svg)

A REST API for a lending library. It handles user accounts, a searchable book catalog and borrowing/returning, and it **stays correct when many users try to borrow the same book at the same moment**.

**Stack:** Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Alembic · JWT (PyJWT + bcrypt) · pytest · Docker Compose · GitHub Actions · Ruff

---

## What it does

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` · `POST /auth/login` → JWT · `GET /auth/me` |
| Catalog | `GET /books?q=&available=&limit=&offset=` (search + pagination) · `GET /books/{id}` |
| Admin | `POST /books` · `PATCH /books/{id}` · `DELETE /books/{id}` |
| Loans | `POST /loans` (borrow) · `POST /loans/{id}/return` · `GET /loans/me` |
| Ops | `GET /health` (checks the DB connection too) |

Business rules: max 3 active loans per user, 14-day loan period, overdue flag, no borrowing the same book twice, admins can't reduce a book's copies below the number currently on loan, and a book with active loans can't be deleted.

Interactive docs: run it, then open **http://localhost:8000/docs**.

## Run it

```bash
# Option A: everything in Docker
docker compose up --build
# API on http://localhost:8000, Postgres on localhost:5432

# create an admin account (needed to add books)
docker compose exec api python -m app.create_admin admin@example.com 'AdminPass123'
```

```bash
# Option B: local Python, Postgres from Docker
docker compose up -d db
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Tests

```bash
docker compose up -d db
docker compose exec db createdb -U postgres lendit_test
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/lendit_test pytest --cov
```

There are 31 tests at 99% line coverage. They run against **real PostgreSQL**, not SQLite, because the locking behaviour below only exists in a real database server. CI runs lint, the migration check, the tests and a Docker smoke test on every push.

---

## The interesting part: a race condition

**The bug.** A naive borrow looks like this:

```python
book = db.get(Book, book_id)  # request A and B both read available_copies = 1
if book.available_copies > 0:  # both pass the check
    book.available_copies -= 1  # both write 0, so 2 loans exist for 1 physical book
```

`tests/test_concurrency.py` starts 20 threads that each try to borrow the **last copy** at the same instant. A `threading.Barrier` releases them all together, and each thread uses its own database connection. With the naive code, **8 to 19 of the 20 users "got" the single copy** in my runs.

**The fix** (`app/services/loans.py`) is `SELECT ... FOR UPDATE`. It locks the book row until the transaction commits, so the second request waits, then re-reads `available_copies = 0` and gets a `409 Conflict`. The user row is locked too, so one user firing 10 parallel requests can't get past the 3-loan limit. Locks are always taken in the same order (user, then book) so that two transactions can never deadlock waiting on each other.

**Defence in depth.** The `books` table also has `CHECK (available_copies >= 0)` constraints, so even a future bug in the app code can't store negative stock.

To see the bug yourself, delete the two `.with_for_update()` calls and run `pytest tests/test_concurrency.py`.

## Performance: why there's a composite index

Every borrow request and `GET /loans/me` run this query:

```sql
SELECT * FROM loans WHERE user_id = :id AND returned_at IS NULL
```

`scripts/benchmark_index.py` loads 1,000,000 loans and times that query with `EXPLAIN ANALYZE`, with and without an index on `(user_id, returned_at)`:

```bash
docker compose exec db createdb -U postgres lendit_bench
BENCH_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/lendit_bench python -m scripts.benchmark_index
```

| | Plan | Median time |
|---|---|---|
| No index | Parallel sequential scan of 1M rows | ~27 ms |
| Composite index | Bitmap index scan | ~0.015 ms |

That's about a 1,700× speed-up on that query. Your numbers will vary by machine, so run it yourself.

## Project layout

```
app/
  main.py            FastAPI app + router wiring
  config.py          settings from environment variables
  db.py              engine, session, get_db dependency
  models.py          SQLAlchemy tables (User, Book, Loan) + constraints + index
  schemas.py         Pydantic request/response models (validation lives here)
  security.py        bcrypt hashing, JWT create/decode
  deps.py            get_current_user / require_admin dependencies
  routers/           HTTP layer: auth, books, loans
  services/loans.py  borrow/return business logic + locking (no HTTP code)
alembic/             database migrations
tests/               pytest suite (API tests + concurrency tests)
scripts/             index benchmark
```

## Design decisions

- **Service layer separate from routers.** Business rules don't know about HTTP, so the concurrency tests call `borrow_book()` directly from threads.
- **Same error for "unknown email" and "wrong password"** stops attackers from finding out which emails are registered.
- **404 (not 403) when returning someone else's loan** avoids revealing that the loan exists.
- **Alembic migrations, not `create_all()` in production.** The schema is versioned, and CI checks that the migrations match the models.
- **Container runs as a non-root user.** Migrations run on container start.

## Possible next steps

Refresh tokens · rate limiting on `/auth/login` · a reservation queue when no copies are free · structured logging
