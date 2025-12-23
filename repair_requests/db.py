from __future__ import annotations

import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

from repair_requests.domain import ISSUE_TYPES, Role, utcnow


def connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def init_db(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).with_name("schema.sql")
    schema = schema_path.read_text(encoding="utf-8")

    with connect(str(path)) as connection:
        connection.executescript(schema)
        _seed_issue_types(connection)
        _seed_default_users(connection)
        connection.commit()


def _seed_issue_types(connection: sqlite3.Connection) -> None:
    for name in ISSUE_TYPES:
        if name == "Не выбрано":
            continue
        connection.execute(
            "INSERT OR IGNORE INTO issue_types(name) VALUES (?)",
            (name,),
        )


def _seed_default_users(connection: sqlite3.Connection) -> None:
    existing = connection.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    if not existing or int(existing["c"]) > 0:
        return

    now = utcnow().isoformat()
    defaults = [
        ("admin", generate_password_hash("admin"), Role.ADMIN.value, "Администратор"),
        (
            "operator",
            generate_password_hash("operator"),
            Role.OPERATOR.value,
            "Оператор",
        ),
        ("master", generate_password_hash("master"), Role.MASTER.value, "Мастер"),
    ]
    connection.executemany(
        "INSERT INTO users(username, password_hash, role, full_name, is_active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        [(u, p, r, f, now) for (u, p, r, f) in defaults],
    )

