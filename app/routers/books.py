from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import Book, Loan
from app.schemas import BookCreate, BookOut, BookPage, BookUpdate

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=BookPage)
def list_books(
    q: str | None = Query(default=None, max_length=100, description="Search in title or author"),
    available: bool | None = Query(default=None, description="Only books with free copies"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(Book)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(Book.title.ilike(pattern) | Book.author.ilike(pattern))
    if available:
        stmt = stmt.where(Book.available_copies > 0)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Book.id).limit(limit).offset(offset)).all()
    return BookPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found")
    return book


@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(body: BookCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    book = Book(**body.model_dump(), available_copies=body.total_copies)
    db.add(book)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A book with this ISBN already exists") from None
    return book


@router.patch("/{book_id}", response_model=BookOut)
def update_book(book_id: int, body: BookUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    book = db.execute(select(Book).where(Book.id == book_id).with_for_update()).scalar_one_or_none()
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found")

    if body.total_copies is not None:
        on_loan = book.total_copies - book.available_copies
        if body.total_copies < on_loan:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, f"{on_loan} copies are on loan; total can't go below that")
        book.available_copies = body.total_copies - on_loan
        book.total_copies = body.total_copies
    if body.title is not None:
        book.title = body.title
    if body.author is not None:
        book.author = body.author
    db.commit()
    return book


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found")
    active = db.scalar(
        select(func.count()).select_from(Loan).where(Loan.book_id == book_id, Loan.returned_at.is_(None))
    )
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Book has active loans")
    db.delete(book)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
