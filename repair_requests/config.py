from __future__ import annotations

from pathlib import Path


class AppConfig:
    SECRET_KEY = "dev-secret-key"
    DATA_DIR = str(Path("data").resolve())
    DATABASE_PATH = str(Path(DATA_DIR) / "app.db")
    QUALITY_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdhZcExx6LSIXxk0ub55mSu-WIh23WYdGG9HY5EZhLDo7P8eA/viewform?usp=sf_link"
