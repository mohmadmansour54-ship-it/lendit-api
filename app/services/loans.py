"""Borrow / return business logic.

Kept separate from the HTTP layer so it can be unit-tested and called
from several threads at once in tests/test_concurrency.py.

THE CONCURRENCY BUG THIS FILE PREVENTS
--------------------------------------
Naive version:
    book = db.get(Book, book_id)          # two requests both read available_copies = 1
    if book.available_copies > 0:         # both pass the check
        book.available_copies -= 1        # both write 0  -> two loans, one physical book

Fix: `SELECT ... FOR UPDATE` locks the row until this transaction commits,
so the second request waits, then re-reads available_copies = 0 and is rejected.
We lock the user row first, then the book row - always in that order -
so two transactions can never wait on each other in a cycle (no deadlock).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Book, Loan, User


class LoanError(Exception):
    """Business-rule violation. `status_code` tells the API layer what to return."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def borrow_book(db: Session, user_id: int, book_id: int) -> Loan:
    # 1) lock the user row: serialises this user's own parallel requests (max-loans rule)
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise LoanError("User not found", 404)

    # 2) lock the book row: serialises everyone competing for the same copies
    book = db.execute(select(Book).where(Book.id == book_id).with_for_update()).scalar_one_or_none()
    if book is None:
        db.rollback()
        raise LoanError("Book not found", 404)

    active = db.scalar(
        select(func.count()).select_from(Loan).where(Loan.user_id == user_id, Loan.returned_at.is_(None))
    )
    if active >= settings.max_active_loans:
        db.rollback()
        raise LoanError(f"Limit reached: max {settings.max_active_loans} active loans")

    already = db.scalar(
        select(func.count())
        .select_from(Loan)
        .where(Loan.user_id == user_id, Loan.book_id == book_id, Loan.returned_at.is_(None))
    )
    if already:
        db.rollback()
        raise LoanError("You already have this book")

    if book.available_copies <= 0:
        db.rollback()
        raise LoanError("No copies available")

    now = datetime.now(UTC)
    book.available_copies -= 1
    loan = Loan(user_id=user_id, book_id=book_id, borrowed_at=now, due_at=now + timedelta(days=settings.loan_days))
    db.add(loan)
    db.commit()  # releases both locks
    return loan


def return_book(db: Session, user_id: int, loan_id: int) -> Loan:
    loan = db.execute(select(Loan).where(Loan.id == loan_id).with_for_update()).scalar_one_or_none()
    if loan is None or loan.user_id != user_id:
        db.rollback()
        raise LoanError("Loan not found", 404)  # 404, not 403: don't reveal other users' loans
    if loan.returned_at is not None:
        db.rollback()
        raise LoanError("Loan already returned")

    book = db.execute(select(Book).where(Book.id == loan.book_id).with_for_update()).scalar_one()
    book.available_copies += 1
    loan.returned_at = datetime.now(UTC)
    db.commit()
    return loan


def is_overdue(loan: Loan, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return loan.returned_at is None and loan.due_at < now
