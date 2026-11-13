from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# ---------- auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt only uses the first 72 bytes


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    is_admin: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- books ----------
class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=200)
    isbn: str = Field(min_length=10, max_length=20)
    total_copies: int = Field(ge=1, le=1000)


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    total_copies: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def not_empty(self):
        if self.title is None and self.author is None and self.total_copies is None:
            raise ValueError("send at least one field to update")
        return self


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    author: str
    isbn: str
    total_copies: int
    available_copies: int


class BookPage(BaseModel):
    items: list[BookOut]
    total: int
    limit: int
    offset: int


# ---------- loans ----------
class LoanCreate(BaseModel):
    book_id: int


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    book_id: int
    borrowed_at: datetime
    due_at: datetime
    returned_at: datetime | None
    is_overdue: bool = False
