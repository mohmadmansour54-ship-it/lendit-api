"""Create (or promote) an admin user.

Usage:  python -m app.create_admin admin@example.com 'StrongPass123'
"""

import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security import hash_password


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python -m app.create_admin EMAIL PASSWORD")
    email, password = sys.argv[1].lower(), sys.argv[2]
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=hash_password(password))
            db.add(user)
        user.is_admin = True
        db.commit()
        print(f"admin ready: {email}")


if __name__ == "__main__":
    main()
