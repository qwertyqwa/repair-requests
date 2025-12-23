from __future__ import annotations

from pathlib import Path

from flask import Flask

from repair_requests.config import AppConfig
from repair_requests.routes import bp
from repair_requests.store import SqliteStore


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(AppConfig())
    if test_config:
        app.config.update(test_config)
        if "DATA_DIR" in test_config and "DATABASE_PATH" not in test_config:
            app.config["DATABASE_PATH"] = str(Path(app.config["DATA_DIR"]) / "app.db")

    store = SqliteStore(app.config["DATABASE_PATH"])
    store.bootstrap()
    app.extensions["store"] = store

    app.register_blueprint(bp)

    return app
