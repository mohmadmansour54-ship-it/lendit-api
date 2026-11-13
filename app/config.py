from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables (or a .env file)."""

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/lendit"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    loan_days: int = 14  # how long a borrower keeps a book
    max_active_loans: int = 3  # per user

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
