from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from repair_requests.db import connect, init_db
from repair_requests.domain import RequestStatus, utcnow


def parse_status(value: str) -> str:
    raw = value.strip()
    try:
        return RequestStatus(raw).value
    except Exception:
        return RequestStatus.NEW.value


def parse_dt(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def get_or_create_client(connection, *, full_name: str, phone: str) -> int:
    row = connection.execute("SELECT id FROM clients WHERE phone = ?", (phone,)).fetchone()
    if row:
        connection.execute("UPDATE clients SET full_name = ? WHERE id = ?", (full_name, int(row["id"])))
        return int(row["id"])
    cursor = connection.execute("INSERT INTO clients(full_name, phone) VALUES(?, ?)", (full_name, phone))
    return int(cursor.lastrowid)


def get_or_create_appliance(connection, *, appliance_type: str, appliance_model: str) -> int:
    row = connection.execute(
        "SELECT id FROM appliances WHERE appliance_type = ? AND appliance_model = ?",
        (appliance_type, appliance_model),
    ).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute(
        "INSERT INTO appliances(appliance_type, appliance_model) VALUES(?, ?)",
        (appliance_type, appliance_model),
    )
    return int(cursor.lastrowid)


def get_or_create_issue_type(connection, *, name: str) -> int | None:
    cleaned = name.strip()
    if not cleaned or cleaned == "Не выбрано":
        return None
    row = connection.execute("SELECT id FROM issue_types WHERE name = ?", (cleaned,)).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute("INSERT INTO issue_types(name) VALUES(?)", (cleaned,))
    return int(cursor.lastrowid)


def get_user_id(connection, *, username: str) -> int | None:
    cleaned = username.strip()
    if not cleaned:
        return None
    row = connection.execute(
        "SELECT id FROM users WHERE username = ? AND is_active = 1",
        (cleaned,),
    ).fetchone()
    return int(row["id"]) if row else None


def next_request_number(connection) -> int:
    row = connection.execute("SELECT MAX(request_number) AS m FROM tickets").fetchone()
    return (int(row["m"]) if row and row["m"] is not None else 0) + 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import tickets from CSV into SQLite DB (Task 2 import helper)."
    )
    parser.add_argument("--db", default="data/app.db", help="Path to SQLite DB file.")
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to tickets CSV file.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    init_db(str(db_path))

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    now = utcnow()
    now_iso = now.isoformat()
    default_due = (now + timedelta(days=3)).isoformat()

    with connect(str(db_path)) as connection:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                appliance_type = (row.get("appliance_type") or "").strip()
                appliance_model = (row.get("appliance_model") or "").strip()
                problem_description = (row.get("problem_description") or "").strip()
                client_name = (row.get("client_name") or "").strip()
                client_phone = (row.get("client_phone") or "").strip()

                if not (appliance_type and appliance_model and problem_description and client_name and client_phone):
                    continue

                issue_type_id = get_or_create_issue_type(connection, name=row.get("issue_type") or "")
                status = parse_status(row.get("status") or "")
                assigned_id = get_user_id(connection, username=row.get("assigned_master_username") or "")
                due_at = parse_dt(row.get("due_at") or "") or default_due

                client_id = get_or_create_client(connection, full_name=client_name, phone=client_phone)
                appliance_id = get_or_create_appliance(
                    connection, appliance_type=appliance_type, appliance_model=appliance_model
                )

                request_number = next_request_number(connection)
                cursor = connection.execute(
                    "INSERT INTO tickets("
                    "request_number, created_at, updated_at, status, client_id, appliance_id, issue_type_id, "
                    "problem_description, assigned_specialist_id, due_at, started_at, completed_at"
                    ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                    (
                        request_number,
                        now_iso,
                        now_iso,
                        status,
                        client_id,
                        appliance_id,
                        issue_type_id,
                        problem_description,
                        assigned_id,
                        due_at,
                    ),
                )
                ticket_id = int(cursor.lastrowid)

                connection.execute(
                    "INSERT INTO status_history(ticket_id, old_status, new_status, changed_by_user_id, changed_at) "
                    "VALUES(?, NULL, ?, 1, ?)",
                    (ticket_id, status, now_iso),
                )

                if assigned_id is not None:
                    connection.execute(
                        "INSERT OR IGNORE INTO ticket_assignees(ticket_id, user_id, role, assigned_by_user_id, assigned_at) "
                        "VALUES(?, ?, 'primary', 1, ?)",
                        (ticket_id, int(assigned_id), now_iso),
                    )

        connection.commit()

    print("Import completed.")


if __name__ == "__main__":
    main()

