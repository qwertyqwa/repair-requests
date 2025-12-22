from __future__ import annotations

from pathlib import Path


class AppConfig:
    SECRET_KEY = "dev-secret-key"
    DATA_DIR = str(Path("data").resolve())
