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
        _migrate(connection)
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
        (
            "manager",
            generate_password_hash("manager"),
            Role.MANAGER.value,
            "Менеджер по качеству",
        ),
    ]
    connection.executemany(
        "INSERT INTO users(username, password_hash, role, full_name, is_active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?) "
        "ON CONFLICT(username) DO NOTHING",
        [(u, p, r, f, now) for (u, p, r, f) in defaults],
    )


def _migrate(connection: sqlite3.Connection) -> None:
    _ensure_users_role_allows_manager(connection)
    _ensure_column_exists(connection, "tickets", "due_at", "ALTER TABLE tickets ADD COLUMN due_at TEXT;")
    _ensure_ticket_assignees_primary_rows(connection)


def _ensure_users_role_allows_manager(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not row or not row["sql"]:
        return
    sql = str(row["sql"])
    if "manager" in sql:
        return

    connection.execute("PRAGMA foreign_keys = OFF;")
    connection.execute("BEGIN;")
    try:
        connection.execute(
            "CREATE TABLE users_new ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username TEXT NOT NULL UNIQUE, "
            "password_hash TEXT NOT NULL, "
            "role TEXT NOT NULL CHECK (role IN ('admin', 'operator', 'master', 'manager')), "
            "full_name TEXT NOT NULL DEFAULT '', "
            "is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)), "
            "created_at TEXT NOT NULL"
            ");"
        )
        connection.execute(
            "INSERT INTO users_new(id, username, password_hash, role, full_name, is_active, created_at) "
            "SELECT id, username, password_hash, role, full_name, is_active, created_at FROM users;"
        )
        connection.execute("DROP TABLE users;")
        connection.execute("ALTER TABLE users_new RENAME TO users;")
        connection.execute("COMMIT;")
    except Exception:
        connection.execute("ROLLBACK;")
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON;")


def _ensure_column_exists(
    connection: sqlite3.Connection, table: str, column: str, ddl: str
) -> None:
    columns = connection.execute(f"PRAGMA table_info({table});").fetchall()
    if any(str(c["name"]) == column for c in columns):
        return
    connection.execute(ddl)


def _ensure_ticket_assignees_primary_rows(connection: sqlite3.Connection) -> None:
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ticket_assignees'"
    ).fetchone()
    if not tables:
        return

    connection.execute(
        "INSERT OR IGNORE INTO ticket_assignees(ticket_id, user_id, role, assigned_by_user_id, assigned_at) "
        "SELECT t.id, t.assigned_specialist_id, 'primary', t.assigned_specialist_id, t.updated_at "
        "FROM tickets t "
        "WHERE t.assigned_specialist_id IS NOT NULL"
    )
