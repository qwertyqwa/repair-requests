from __future__ import annotations

from flask import Blueprint

bp = Blueprint("web", __name__)


@bp.get("/")
def index():
    return "OK"

