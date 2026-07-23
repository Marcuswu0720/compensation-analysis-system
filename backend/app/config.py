import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    secret_key: str = "dev-secret-change-me"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    session_cookie_name: str = "comp_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    upload_dir: str = str(BASE_DIR / "data" / "uploads")

    class Config:
        env_file = str(BASE_DIR.parent / ".env")


settings = Settings()
os.makedirs(BASE_DIR / "data", exist_ok=True)
os.makedirs(settings.upload_dir, exist_ok=True)
