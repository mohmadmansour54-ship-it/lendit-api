"""Measure what the composite index on loans(user_id, returned_at) buys us.

The query behind GET /loans/me (and the max-loans check in every borrow) is:
    SELECT * FROM loans WHERE user_id = :id AND returned_at IS NULL

This script fills a SEPARATE benchmark database with fake data, then runs that
query with and without the index using EXPLAIN ANALYZE and prints the timings.

Usage (needs an empty database, e.g. `createdb lendit_bench`):
    BENCH_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/lendit_bench \
        python -m scripts.benchmark_index --loans 1000000
"""

import argparse
import os
import re
import statistics

from sqlalchemy import create_engine, text

import app.models  # noqa: F401  (registers tables)
from app.db import Base

QUERY = "SELECT * FROM loans WHERE user_id = :uid AND returned_at IS NULL"


def seed(conn, n_users: int, n_books: int, n_loans: int) -> None:
    print(f"seeding {n_users:,} users, {n_books:,} books, {n_loans:,} loans ...")
    conn.execute(text("TRUNCATE loans, books, users RESTART IDENTITY CASCADE"))
    conn.execute(
        text(
            "INSERT INTO users (email, password_hash, is_admin) "
            "SELECT 'user' || g || '@example.com', 'x', false FROM generate_series(1, :n) g"
        ),
        {"n": n_users},
    )
    conn.execute(
        text(
            "INSERT INTO books (title, author, isbn, total_copies, available_copies) "
            "SELECT 'Book ' || g, 'Author ' || (g % 500), lpad(g::text, 13, '0'), 10, 10 FROM generate_series(1, :n) g"
        ),
        {"n": n_books},
    )
    # ~95% of loans are already returned, like a real library history
    conn.execute(
        text(
            "INSERT INTO loans (user_id, book_id, borrowed_at, due_at, returned_at) "
            "SELECT 1 + (random() * (:u - 1))::int, 1 + (random() * (:b - 1))::int, "
            "       now() - interval '30 days', now() - interval '16 days', "
            "       CASE WHEN random() < 0.95 THEN now() - interval '20 days' END "
            "FROM generate_series(1, :n)"
        ),
        {"u": n_users, "b": n_books, "n": n_loans},
    )
    conn.execute(text("ANALYZE"))


def time_query(conn, runs: int, n_users: int) -> tuple[float, str]:
    times, plan_first = [], ""
    for i in range(runs):
        uid = 1 + (i * 7919) % n_users  # spread over different users
        rows = conn.execute(text("EXPLAIN ANALYZE " + QUERY), {"uid": uid}).scalars().all()
        plan = "\n".join(rows)
        plan_first = plan_first or rows[0]
        times.append(float(re.search(r"Execution Time: ([\d.]+) ms", plan).group(1)))
    return statistics.median(times), plan_first


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=int, default=10_000)
    p.add_argument("--books", type=int, default=20_000)
    p.add_argument("--loans", type=int, default=1_000_000)
    p.add_argument("--runs", type=int, default=50)
    args = p.parse_args()

    url = os.environ.get("BENCH_DATABASE_URL")
    if not url:
        raise SystemExit("set BENCH_DATABASE_URL to an EMPTY database (it will be wiped)")
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        seed(conn, args.users, args.books, args.loans)

    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_loans_user_returned"))
        conn.execute(text("ANALYZE loans"))
        slow, slow_plan = time_query(conn, args.runs, args.users)

        conn.execute(text("CREATE INDEX ix_loans_user_returned ON loans (user_id, returned_at)"))
        conn.execute(text("ANALYZE loans"))
        fast, fast_plan = time_query(conn, args.runs, args.users)

    print(f"\nquery: {QUERY}   ({args.loans:,} loans, median of {args.runs} runs)")
    print(f"  without index: {slow:8.3f} ms   plan: {slow_plan.strip()}")
    print(f"  with index:    {fast:8.3f} ms   plan: {fast_plan.strip()}")
    print(f"  speed-up:      {slow / fast:,.0f}x")


if __name__ == "__main__":
    main()
