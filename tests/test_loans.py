from datetime import UTC, datetime, timedelta

from app.models import Loan
from app.services.loans import is_overdue
from tests.conftest import login, make_book, make_user


def test_borrow_and_return(client, db, user_headers):
    book = make_book(db, copies=1)

    r = client.post("/loans", json={"book_id": book.id}, headers=user_headers)
    assert r.status_code == 201
    loan = r.json()
    assert client.get(f"/books/{book.id}", headers=user_headers).json()["available_copies"] == 0

    r = client.post(f"/loans/{loan['id']}/return", headers=user_headers)
    assert r.status_code == 200 and r.json()["returned_at"] is not None
    assert client.get(f"/books/{book.id}", headers=user_headers).json()["available_copies"] == 1


def test_no_copies_left(client, db, user_headers):
    book = make_book(db, copies=1)
    make_user(db, "other@example.com")
    other = login(client, "other@example.com")

    assert client.post("/loans", json={"book_id": book.id}, headers=other).status_code == 201
    r = client.post("/loans", json={"book_id": book.id}, headers=user_headers)
    assert r.status_code == 409 and "No copies" in r.json()["detail"]


def test_cannot_borrow_same_book_twice(client, db, user_headers):
    book = make_book(db, copies=5)
    assert client.post("/loans", json={"book_id": book.id}, headers=user_headers).status_code == 201
    assert client.post("/loans", json={"book_id": book.id}, headers=user_headers).status_code == 409


def test_max_active_loans(client, db, user_headers):
    books = [make_book(db, isbn=f"978000000010{i}") for i in range(4)]
    for b in books[:3]:
        assert client.post("/loans", json={"book_id": b.id}, headers=user_headers).status_code == 201
    r = client.post("/loans", json={"book_id": books[3].id}, headers=user_headers)
    assert r.status_code == 409 and "Limit" in r.json()["detail"]


def test_cannot_return_twice(client, db, user_headers):
    book = make_book(db)
    loan_id = client.post("/loans", json={"book_id": book.id}, headers=user_headers).json()["id"]
    assert client.post(f"/loans/{loan_id}/return", headers=user_headers).status_code == 200
    assert client.post(f"/loans/{loan_id}/return", headers=user_headers).status_code == 409


def test_cannot_return_someone_elses_loan(client, db, user_headers):
    book = make_book(db)
    loan_id = client.post("/loans", json={"book_id": book.id}, headers=user_headers).json()["id"]
    make_user(db, "thief@example.com")
    thief = login(client, "thief@example.com")
    assert client.post(f"/loans/{loan_id}/return", headers=thief).status_code == 404


def test_borrow_missing_book(client, user_headers):
    assert client.post("/loans", json={"book_id": 12345}, headers=user_headers).status_code == 404


def test_my_loans_active_filter(client, db, user_headers):
    b1, b2 = make_book(db, isbn="9780000000201"), make_book(db, isbn="9780000000202")
    l1 = client.post("/loans", json={"book_id": b1.id}, headers=user_headers).json()["id"]
    client.post("/loans", json={"book_id": b2.id}, headers=user_headers)
    client.post(f"/loans/{l1}/return", headers=user_headers)

    assert len(client.get("/loans/me", headers=user_headers).json()) == 1
    assert len(client.get("/loans/me?active_only=false", headers=user_headers).json()) == 2


def test_is_overdue():
    now = datetime.now(UTC)
    late = Loan(borrowed_at=now - timedelta(days=20), due_at=now - timedelta(days=6), returned_at=None)
    on_time = Loan(borrowed_at=now, due_at=now + timedelta(days=14), returned_at=None)
    returned_late = Loan(borrowed_at=now - timedelta(days=20), due_at=now - timedelta(days=6), returned_at=now)
    assert is_overdue(late) is True
    assert is_overdue(on_time) is False
    assert is_overdue(returned_late) is False
