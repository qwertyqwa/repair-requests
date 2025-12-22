from __future__ import annotations

from flask import Flask

from repair_requests.config import AppConfig
from repair_requests.routes import bp
from repair_requests.store import JsonStore


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(AppConfig())
    if test_config:
        app.config.update(test_config)

    store = JsonStore(app.config["DATA_DIR"])
    store.bootstrap()
    app.extensions["store"] = store

    app.register_blueprint(bp)

    return app

