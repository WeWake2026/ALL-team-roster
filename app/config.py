import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "ShiftFlow Pro - Workforce & Leave ERP"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "msedcl-shiftflow-super-secret-key-2026")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./shiftflow.db")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1")

    class Config:
        env_file = ".env"

settings = Settings()
