"""Test setup.

Tests run against a REAL PostgreSQL database (not SQLite), because the
row-locking behaviour we test (SELECT ... FOR UPDATE) only exists there.
Set TEST_DATABASE_URL to point at an empty test database.
"""

import os

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/lendit_test")
os.environ["DATABASE_URL"] = TEST_DB  # must happen before `app` is imported
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Book, User  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "Password123"


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_tables():
    """Every test starts with empty tables."""
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE loans, books, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_user(db, email: str, is_admin: bool = False) -> User:
    user = User(email=email, password_hash=hash_password(PASSWORD), is_admin=is_admin)
    db.add(user)
    db.commit()
    return user


def make_book(db, copies: int = 1, isbn: str = "9780000000001", title="Clean Code", author="Robert Martin") -> Book:
    book = Book(title=title, author=author, isbn=isbn, total_copies=copies, available_copies=copies)
    db.add(book)
    db.commit()
    return book


def login(client, email: str) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def user_headers(client, db):
    make_user(db, "student@example.com")
    return login(client, "student@example.com")


@pytest.fixture
def admin_headers(client, db):
    make_user(db, "admin@example.com", is_admin=True)
    return login(client, "admin@example.com")
