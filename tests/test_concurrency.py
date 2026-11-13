"""Race-condition tests.

Many threads try to borrow at the *same instant* (a Barrier releases them together).
Each thread uses its own DB session = its own connection = a separate transaction,
exactly like separate HTTP requests hitting the server in parallel.

To see the bug these tests catch: remove `.with_for_update()` from the two
SELECTs in app/services/loans.py and run `pytest tests/test_concurrency.py`.
"""

import threading

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Book, Loan
from app.services.loans import LoanError, borrow_book
from tests.conftest import make_book, make_user

N_USERS = 20


def race(fn_args: list[tuple[int, int]]) -> tuple[int, int]:
    """Run borrow_book for every (user_id, book_id) simultaneously. Returns (successes, rejections)."""
    barrier = threading.Barrier(len(fn_args))
    results: list[str] = []
    lock = threading.Lock()

    def worker(user_id: int, book_id: int):
        with SessionLocal() as db:
            barrier.wait()
            try:
                borrow_book(db, user_id, book_id)
                outcome = "ok"
            except LoanError:
                outcome = "rejected"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=a) for a in fn_args]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results.count("ok"), results.count("rejected")


def test_last_copy_goes_to_exactly_one_user(db):
    book = make_book(db, copies=1)
    users = [make_user(db, f"u{i}@example.com") for i in range(N_USERS)]

    ok, rejected = race([(u.id, book.id) for u in users])

    assert (ok, rejected) == (1, N_USERS - 1)
    db.expire_all()
    assert db.get(Book, book.id).available_copies == 0
    assert db.scalar(select(func.count()).select_from(Loan)) == 1


def test_stock_never_goes_negative(db):
    book = make_book(db, copies=5)
    users = [make_user(db, f"u{i}@example.com") for i in range(N_USERS)]

    ok, _ = race([(u.id, book.id) for u in users])

    assert ok == 5
    db.expire_all()
    assert db.get(Book, book.id).available_copies == 0


def test_one_user_parallel_requests_respect_loan_limit(db):
    """Same user fires 10 borrow requests for 10 different books at once: only 3 may succeed."""
    user = make_user(db, "greedy@example.com")
    books = [make_book(db, isbn=f"97800000003{i:02d}") for i in range(10)]

    ok, rejected = race([(user.id, b.id) for b in books])

    assert (ok, rejected) == (3, 7)
