from tests.conftest import make_book

NEW_BOOK = {"title": "The Pragmatic Programmer", "author": "Hunt & Thomas", "isbn": "9780135957059", "total_copies": 3}


def test_admin_can_create_book(client, admin_headers):
    r = client.post("/books", json=NEW_BOOK, headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["available_copies"] == 3


def test_regular_user_cannot_create_book(client, user_headers):
    assert client.post("/books", json=NEW_BOOK, headers=user_headers).status_code == 403


def test_duplicate_isbn_rejected(client, admin_headers):
    assert client.post("/books", json=NEW_BOOK, headers=admin_headers).status_code == 201
    assert client.post("/books", json=NEW_BOOK, headers=admin_headers).status_code == 409


def test_invalid_book_rejected(client, admin_headers):
    bad = {**NEW_BOOK, "total_copies": 0}
    assert client.post("/books", json=bad, headers=admin_headers).status_code == 422


def test_search_and_pagination(client, db, user_headers):
    for i in range(25):
        make_book(db, isbn=f"97800000000{i:02d}", title=f"Book {i}", author="Alice" if i % 2 else "Bob")

    page = client.get("/books?limit=10&offset=20", headers=user_headers).json()
    assert page["total"] == 25 and len(page["items"]) == 5

    alice = client.get("/books?q=alice&limit=100", headers=user_headers).json()
    assert alice["total"] == 12  # odd i in 0..24
    assert all(b["author"] == "Alice" for b in alice["items"])


def test_limit_is_capped(client, user_headers):
    assert client.get("/books?limit=1000", headers=user_headers).status_code == 422


def test_get_missing_book_404(client, user_headers):
    assert client.get("/books/999", headers=user_headers).status_code == 404


def test_update_copies_keeps_loans_consistent(client, db, admin_headers, user_headers):
    book = make_book(db, copies=2)
    client.post("/loans", json={"book_id": book.id}, headers=user_headers)  # 1 on loan

    r = client.patch(f"/books/{book.id}", json={"total_copies": 5}, headers=admin_headers)
    assert r.json()["available_copies"] == 4

    # total must stay >= copies currently borrowed (1 here)
    assert client.patch(f"/books/{book.id}", json={"total_copies": 0}, headers=admin_headers).status_code == 422
    shrink = client.patch(f"/books/{book.id}", json={"total_copies": 1}, headers=admin_headers)
    assert shrink.status_code == 200 and shrink.json()["available_copies"] == 0


def test_cannot_delete_book_on_loan(client, db, admin_headers, user_headers):
    book = make_book(db)
    client.post("/loans", json={"book_id": book.id}, headers=user_headers)
    assert client.delete(f"/books/{book.id}", headers=admin_headers).status_code == 409


def test_available_filter(client, db, user_headers):
    free = make_book(db, isbn="9780000000301", copies=1)
    taken = make_book(db, isbn="9780000000302", copies=1)
    client.post("/loans", json={"book_id": taken.id}, headers=user_headers)
    ids = [b["id"] for b in client.get("/books?available=true", headers=user_headers).json()["items"]]
    assert ids == [free.id]


def test_update_title_author(client, db, admin_headers):
    book = make_book(db)
    r = client.patch(
        f"/books/{book.id}", json={"title": "Clean Code 2e", "author": "R. C. Martin"}, headers=admin_headers
    )
    assert r.json()["title"] == "Clean Code 2e" and r.json()["author"] == "R. C. Martin"


def test_update_needs_a_field_and_existing_book(client, db, admin_headers):
    book = make_book(db)
    assert client.patch(f"/books/{book.id}", json={}, headers=admin_headers).status_code == 422
    assert client.patch("/books/999", json={"title": "x"}, headers=admin_headers).status_code == 404


def test_delete_book(client, db, admin_headers, user_headers):
    book = make_book(db)
    assert client.delete(f"/books/{book.id}", headers=admin_headers).status_code == 204
    assert client.get(f"/books/{book.id}", headers=user_headers).status_code == 404
    assert client.delete(f"/books/{book.id}", headers=admin_headers).status_code == 404
