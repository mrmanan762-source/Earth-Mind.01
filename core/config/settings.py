import os
from pydantic import BaseModel

class Settings(BaseModel):
    app_name: str = "EarthMind"
    environment: str = os.getenv("EARTHMIND_ENV", "development")
    version: str = "0.1.0"
    db_path: str = os.getenv("EARTHMIND_DB_PATH", "earthmind.db")
    log_level: str = os.getenv("EARTHMIND_LOG_LEVEL", "INFO")

settings = Settings()
