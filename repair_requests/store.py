from __future__ import annotations

from pathlib import Path


class JsonStore:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)

    def bootstrap(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

