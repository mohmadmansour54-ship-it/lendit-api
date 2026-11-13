from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Loan, User
from app.schemas import LoanCreate, LoanOut
from app.services.loans import LoanError, borrow_book, is_overdue, return_book

router = APIRouter(prefix="/loans", tags=["loans"])


def to_out(loan: Loan) -> LoanOut:
    out = LoanOut.model_validate(loan)
    out.is_overdue = is_overdue(loan)
    return out


@router.post("", response_model=LoanOut, status_code=status.HTTP_201_CREATED)
def borrow(body: LoanCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return to_out(borrow_book(db, user.id, body.book_id))
    except LoanError as e:
        raise HTTPException(e.status_code, e.message) from None


@router.post("/{loan_id}/return", response_model=LoanOut)
def give_back(loan_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return to_out(return_book(db, user.id, loan_id))
    except LoanError as e:
        raise HTTPException(e.status_code, e.message) from None


@router.get("/me", response_model=list[LoanOut])
def my_loans(
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Loan).where(Loan.user_id == user.id)
    if active_only:
        stmt = stmt.where(Loan.returned_at.is_(None))
    return [to_out(loan) for loan in db.scalars(stmt.order_by(Loan.borrowed_at.desc()))]
