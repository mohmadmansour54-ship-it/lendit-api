from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import auth, books, loans

app = FastAPI(
    title="LendIt API",
    description="Book-lending REST API: auth, catalog, and concurrency-safe borrowing.",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(books.router)
app.include_router(loans.router)


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))  # proves the DB is reachable, not just the web process
    return {"status": "ok"}
