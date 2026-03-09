import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://asmo_user:asmo_pass@localhost:5432/asmo"
    )