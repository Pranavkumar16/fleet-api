# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./fleet.db"
    SECRET_KEY: str = "super-secret"

    # optional: read from .env and allow FLEET_* env vars
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FLEET_",
        case_sensitive=False,
    )

settings = Settings()
