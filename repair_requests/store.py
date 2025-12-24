from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from repair_requests.db import connect, init_db
from repair_requests.domain import (
    NotificationItem,
    RepairRequest,
    RequestStatus,
    STATUS_LABELS,
    Role,
    StatusHistoryItem,
    TicketComment,
    TicketPart,
    User,
    utcnow,
)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class SqliteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def bootstrap(self) -> None:
        init_db(self.db_path)

    def verify_password(self, username: str, password: str) -> bool:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE username = ? AND is_active = 1",
                (username,),
            ).fetchone()
            if not row:
                return False
            return check_password_hash(row["password_hash"], password)

    def get_user(self, username: str) -> User | None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, role, full_name, is_active "
                "FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row:
                return None
            return User(
                id=int(row["id"]),
                username=str(row["username"]),
                password_hash=str(row["password_hash"]),
                role=Role(str(row["role"])),
                full_name=str(row["full_name"] or ""),
                is_active=bool(int(row["is_active"])),
            )

    def get_user_id(self, username: str) -> int | None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM users WHERE username = ? AND is_active = 1",
                (username,),
            ).fetchone()
            return int(row["id"]) if row else None

    def list_masters(self) -> list[User]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT id, username, password_hash, role, full_name, is_active "
                "FROM users WHERE role = ? AND is_active = 1 ORDER BY username",
                (Role.MASTER.value,),
            ).fetchall()
            return [
                User(
                    id=int(r["id"]),
                    username=str(r["username"]),
                    password_hash=str(r["password_hash"]),
                    role=Role(str(r["role"])),
                    full_name=str(r["full_name"] or ""),
                    is_active=bool(int(r["is_active"])),
                )
                for r in rows
            ]

    def list_users(self) -> list[User]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT id, username, password_hash, role, full_name, is_active "
                "FROM users ORDER BY username"
            ).fetchall()
            return [
                User(
                    id=int(r["id"]),
                    username=str(r["username"]),
                    password_hash=str(r["password_hash"]),
                    role=Role(str(r["role"])),
                    full_name=str(r["full_name"] or ""),
                    is_active=bool(int(r["is_active"])),
                )
                for r in rows
            ]

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: Role,
        full_name: str,
        is_active: bool = True,
    ) -> None:
        now = utcnow().isoformat()
        with connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO users(username, password_hash, role, full_name, is_active, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (
                    username,
                    generate_password_hash(password),
                    role.value,
                    full_name,
                    1 if is_active else 0,
                    now,
                ),
            )
            connection.commit()

    def set_user_active(self, user_id: int, is_active: bool) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, user_id),
            )
            connection.commit()

    def list_requests(self, assigned_user_id: int | None = None) -> list[RepairRequest]:
        sql = self._tickets_select_sql()
        params: tuple[object, ...] = ()
        if assigned_user_id is not None:
            sql += (
                " WHERE EXISTS (SELECT 1 FROM ticket_assignees ta "
                "WHERE ta.ticket_id = t.id AND ta.user_id = ?)"
            )
            params = (assigned_user_id,)
        sql += " ORDER BY t.request_number DESC"
        with connect(self.db_path) as connection:
            rows = connection.execute(sql, params).fetchall()
            return [self._row_to_ticket(r) for r in rows]

    def get_request(self, number: int) -> RepairRequest | None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                self._tickets_select_sql() + " WHERE t.request_number = ?",
                (number,),
            ).fetchone()
            return self._row_to_ticket(row) if row else None

    def create_request(
        self,
        *,
        appliance_type: str,
        appliance_model: str,
        issue_type: str | None,
        problem_description: str,
        client_name: str,
        client_phone: str,
        technician_username: str | None,
        created_by_user_id: int,
    ) -> RepairRequest:
        now_dt = utcnow()
        now = now_dt.isoformat()
        due_at = (now_dt + timedelta(days=3)).isoformat()
        with connect(self.db_path) as connection:
            client_id = self._get_or_create_client(
                connection,
                full_name=client_name,
                phone=client_phone,
            )
            appliance_id = self._get_or_create_appliance(
                connection,
                appliance_type=appliance_type,
                appliance_model=appliance_model,
            )
            issue_type_id = self._get_issue_type_id(connection, issue_type)
            assigned_specialist_id = (
                self._get_user_id_for_username(connection, technician_username)
                if technician_username
                else None
            )
            request_number = self._next_request_number(connection)

            cursor = connection.execute(
                "INSERT INTO tickets("
                "request_number, created_at, updated_at, status, client_id, appliance_id, "
                "issue_type_id, problem_description, assigned_specialist_id, due_at, started_at, completed_at"
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                (
                    request_number,
                    now,
                    now,
                    RequestStatus.NEW.value,
                    client_id,
                    appliance_id,
                    issue_type_id,
                    problem_description,
                    assigned_specialist_id,
                    due_at,
                ),
            )
            ticket_id = int(cursor.lastrowid)

            connection.execute(
                "INSERT INTO status_history(ticket_id, old_status, new_status, changed_by_user_id, changed_at) "
                "VALUES(?, NULL, ?, ?, ?)",
                (ticket_id, RequestStatus.NEW.value, created_by_user_id, now),
            )

            if assigned_specialist_id is not None:
                connection.execute(
                    "INSERT OR IGNORE INTO ticket_assignees(ticket_id, user_id, role, assigned_by_user_id, assigned_at) "
                    "VALUES(?, ?, 'primary', ?, ?)",
                    (ticket_id, int(assigned_specialist_id), created_by_user_id, now),
                )
                self._create_notification(
                    connection,
                    user_id=assigned_specialist_id,
                    ticket_id=ticket_id,
                    message=f"Вам назначена заявка №{request_number}.",
                    created_at=now,
                )

            connection.commit()

        created = self.get_request(request_number)
        if not created:
            raise RuntimeError("Failed to create request")
        return created

    def update_request(
        self,
        number: int,
        *,
        appliance_type: str | None = None,
        appliance_model: str | None = None,
        issue_type: str | None = None,
        problem_description: str | None = None,
        client_name: str | None = None,
        client_phone: str | None = None,
        status: RequestStatus | None = None,
        technician_username: str | None = None,
        changed_by_user_id: int,
    ) -> RepairRequest:
        now = utcnow().isoformat()
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id, status, assigned_specialist_id, client_id, appliance_id "
                "FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                raise KeyError("Request not found")

            ticket_id = int(row["id"])
            old_status = str(row["status"])
            old_assigned_id = row["assigned_specialist_id"]
            client_id = int(row["client_id"])
            appliance_id = int(row["appliance_id"])

            if client_name is not None or client_phone is not None:
                connection.execute(
                    "UPDATE clients SET full_name = COALESCE(?, full_name), phone = COALESCE(?, phone) WHERE id = ?",
                    (client_name, client_phone, client_id),
                )

            if appliance_type is not None or appliance_model is not None:
                updated_type = (
                    appliance_type
                    if appliance_type is not None
                    else connection.execute(
                        "SELECT appliance_type FROM appliances WHERE id = ?",
                        (appliance_id,),
                    ).fetchone()["appliance_type"]
                )
                updated_model = (
                    appliance_model
                    if appliance_model is not None
                    else connection.execute(
                        "SELECT appliance_model FROM appliances WHERE id = ?",
                        (appliance_id,),
                    ).fetchone()["appliance_model"]
                )
                new_appliance_id = self._get_or_create_appliance(
                    connection,
                    appliance_type=str(updated_type),
                    appliance_model=str(updated_model),
                )
            else:
                new_appliance_id = appliance_id

            new_issue_type_id = (
                self._get_issue_type_id(connection, issue_type)
                if issue_type is not None
                else None
            )

            new_assigned_id = (
                self._get_user_id_for_username(connection, technician_username)
                if technician_username is not None and technician_username != ""
                else None
            )
            if technician_username is None:
                new_assigned_id = old_assigned_id

            started_at = None
            completed_at = None
            next_status_value = old_status
            if status is not None and status.value != old_status:
                next_status_value = status.value
                if next_status_value == RequestStatus.IN_PROGRESS.value:
                    started_at = now
                if next_status_value == RequestStatus.READY.value:
                    completed_at = now

            connection.execute(
                "UPDATE tickets SET "
                "updated_at = ?, "
                "status = ?, "
                "appliance_id = ?, "
                "issue_type_id = COALESCE(?, issue_type_id), "
                "problem_description = COALESCE(?, problem_description), "
                "assigned_specialist_id = ?, "
                "started_at = COALESCE(started_at, ?), "
                "completed_at = COALESCE(completed_at, ?) "
                "WHERE id = ?",
                (
                    now,
                    next_status_value,
                    new_appliance_id,
                    new_issue_type_id,
                    problem_description,
                    new_assigned_id,
                    started_at,
                    completed_at,
                    ticket_id,
                ),
            )

            if new_assigned_id is not None and new_assigned_id != old_assigned_id:
                connection.execute(
                    "UPDATE ticket_assignees SET role = 'assistant' WHERE ticket_id = ? AND role = 'primary'",
                    (ticket_id,),
                )
                connection.execute(
                    "INSERT INTO ticket_assignees(ticket_id, user_id, role, assigned_by_user_id, assigned_at) "
                    "VALUES(?, ?, 'primary', ?, ?) "
                    "ON CONFLICT(ticket_id, user_id) DO UPDATE SET role='primary', assigned_by_user_id=excluded.assigned_by_user_id, assigned_at=excluded.assigned_at",
                    (ticket_id, int(new_assigned_id), changed_by_user_id, now),
                )

            if status is not None and status.value != old_status:
                connection.execute(
                    "INSERT INTO status_history(ticket_id, old_status, new_status, changed_by_user_id, changed_at) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (ticket_id, old_status, status.value, changed_by_user_id, now),
                )
                self._create_status_change_notifications(
                    connection,
                    ticket_id=ticket_id,
                    request_number=number,
                    new_status=status.value,
                    changed_by_user_id=changed_by_user_id,
                    created_at=now,
                )

            if new_assigned_id != old_assigned_id and new_assigned_id is not None:
                self._create_notification(
                    connection,
                    user_id=int(new_assigned_id),
                    ticket_id=ticket_id,
                    message=f"Вам назначена заявка №{number}.",
                    created_at=now,
                )

            connection.commit()

        updated = self.get_request(number)
        if not updated:
            raise RuntimeError("Failed to update request")
        return updated

    def delete_request(self, number: int) -> None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                return
            connection.execute("DELETE FROM tickets WHERE id = ?", (int(row["id"]),))
            connection.commit()

    def search_requests(
        self,
        *,
        query: str,
        status: RequestStatus | None = None,
        assigned_user_id: int | None = None,
    ) -> list[RepairRequest]:
        needle = query.strip()
        filters: list[str] = []
        params: list[object] = []

        if status is not None:
            filters.append("t.status = ?")
            params.append(status.value)

        if assigned_user_id is not None:
            filters.append(
                "EXISTS (SELECT 1 FROM ticket_assignees ta WHERE ta.ticket_id = t.id AND ta.user_id = ?)"
            )
            params.append(assigned_user_id)

        if needle:
            if needle.isdigit():
                filters.append("t.request_number = ?")
                params.append(int(needle))
            else:
                like = f"%{needle.lower()}%"
                filters.append(
                    "("
                    "LOWER(c.full_name) LIKE ? OR "
                    "LOWER(c.phone) LIKE ? OR "
                    "LOWER(a.appliance_type) LIKE ? OR "
                    "LOWER(a.appliance_model) LIKE ? OR "
                    "LOWER(t.problem_description) LIKE ? OR "
                    "LOWER(COALESCE(it.name, '')) LIKE ?"
                    ")"
                )
                params.extend([like, like, like, like, like, like])

        where_sql = f" WHERE {' AND '.join(filters)}" if filters else ""
        sql = self._tickets_select_sql() + where_sql + " ORDER BY t.request_number DESC"

        with connect(self.db_path) as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
            return [self._row_to_ticket(r) for r in rows]

    def is_user_assigned_to_ticket(self, number: int, user_id: int) -> bool:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT t.id, t.assigned_specialist_id FROM tickets t WHERE t.request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                return False
            if row["assigned_specialist_id"] is not None and int(row["assigned_specialist_id"]) == user_id:
                return True
            ticket_id = int(row["id"])
            assigned = connection.execute(
                "SELECT 1 FROM ticket_assignees WHERE ticket_id = ? AND user_id = ?",
                (ticket_id, user_id),
            ).fetchone()
            return assigned is not None

    def list_assignees(self, number: int) -> list[tuple[str, str]]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                return []
            ticket_id = int(row["id"])
            rows = connection.execute(
                "SELECT u.username, ta.role "
                "FROM ticket_assignees ta "
                "JOIN users u ON u.id = ta.user_id "
                "WHERE ta.ticket_id = ? "
                "ORDER BY CASE ta.role WHEN 'primary' THEN 0 ELSE 1 END, u.username",
                (ticket_id,),
            ).fetchall()
            return [(str(r["username"]), str(r["role"])) for r in rows]

    def add_assignee(
        self,
        number: int,
        *,
        master_username: str,
        role: str,
        assigned_by_user_id: int,
    ) -> None:
        if role not in {"primary", "assistant"}:
            raise ValueError("Invalid assignee role")

        now = utcnow().isoformat()
        with connect(self.db_path) as connection:
            ticket_row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not ticket_row:
                raise KeyError("Request not found")
            ticket_id = int(ticket_row["id"])

            user_row = connection.execute(
                "SELECT id FROM users WHERE username = ? AND role = ? AND is_active = 1",
                (master_username, Role.MASTER.value),
            ).fetchone()
            if not user_row:
                raise ValueError("Master not found")
            master_id = int(user_row["id"])

            if role == "primary":
                connection.execute(
                    "UPDATE ticket_assignees SET role = 'assistant' WHERE ticket_id = ? AND role = 'primary'",
                    (ticket_id,),
                )
                connection.execute(
                    "UPDATE tickets SET assigned_specialist_id = ?, updated_at = ? WHERE id = ?",
                    (master_id, now, ticket_id),
                )

            connection.execute(
                "INSERT INTO ticket_assignees(ticket_id, user_id, role, assigned_by_user_id, assigned_at) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(ticket_id, user_id) DO UPDATE SET role=excluded.role, assigned_by_user_id=excluded.assigned_by_user_id, assigned_at=excluded.assigned_at",
                (ticket_id, master_id, role, assigned_by_user_id, now),
            )

            self._create_notification(
                connection,
                user_id=master_id,
                ticket_id=ticket_id,
                message=f"Вас привлекли к заявке №{number} (роль: {role}).",
                created_at=now,
            )

            connection.commit()

    def extend_deadline(
        self,
        number: int,
        *,
        new_due_at: datetime,
        client_confirmed: bool,
        note: str,
        extended_by_user_id: int,
    ) -> None:
        now = utcnow().isoformat()
        new_due = new_due_at.isoformat()
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id, due_at FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                raise KeyError("Request not found")
            ticket_id = int(row["id"])
            old_due = str(row["due_at"]) if row["due_at"] is not None else None

            connection.execute(
                "UPDATE tickets SET due_at = ?, updated_at = ? WHERE id = ?",
                (new_due, now, ticket_id),
            )
            connection.execute(
                "INSERT INTO deadline_extensions(ticket_id, old_due_at, new_due_at, client_confirmed, note, extended_by_user_id, extended_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket_id,
                    old_due,
                    new_due,
                    1 if client_confirmed else 0,
                    note,
                    extended_by_user_id,
                    now,
                ),
            )

            assignees = connection.execute(
                "SELECT user_id FROM ticket_assignees WHERE ticket_id = ?",
                (ticket_id,),
            ).fetchall()
            for a in assignees:
                self._create_notification(
                    connection,
                    user_id=int(a["user_id"]),
                    ticket_id=ticket_id,
                    message=f"По заявке №{number} продлён срок выполнения.",
                    created_at=now,
                )

            connection.commit()

    def list_deadline_extensions(self, number: int) -> list[dict[str, object]]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                return []
            ticket_id = int(row["id"])
            rows = connection.execute(
                "SELECT de.id, de.old_due_at, de.new_due_at, de.client_confirmed, de.note, u.username AS extended_by, de.extended_at "
                "FROM deadline_extensions de "
                "JOIN users u ON u.id = de.extended_by_user_id "
                "WHERE de.ticket_id = ? "
                "ORDER BY de.id DESC",
                (ticket_id,),
            ).fetchall()
            items: list[dict[str, object]] = []
            for r in rows:
                items.append(
                    {
                        "id": int(r["id"]),
                        "old_due_at": parse_dt(str(r["old_due_at"]) if r["old_due_at"] else None),
                        "new_due_at": datetime.fromisoformat(str(r["new_due_at"])),
                        "client_confirmed": bool(int(r["client_confirmed"])),
                        "note": str(r["note"] or ""),
                        "extended_by": str(r["extended_by"]),
                        "extended_at": datetime.fromisoformat(str(r["extended_at"])),
                    }
                )
            return items

    def request_help(
        self, number: int, *, requested_by_user_id: int, message: str
    ) -> None:
        now = utcnow().isoformat()
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                raise KeyError("Request not found")
            ticket_id = int(row["id"])

            connection.execute(
                "INSERT INTO ticket_comments(ticket_id, user_id, body, created_at) VALUES(?, ?, ?, ?)",
                (ticket_id, requested_by_user_id, f"[HELP] {message}", now),
            )

            managers = connection.execute(
                "SELECT id FROM users WHERE role = ? AND is_active = 1",
                (Role.MANAGER.value,),
            ).fetchall()
            for m in managers:
                self._create_notification(
                    connection,
                    user_id=int(m["id"]),
                    ticket_id=ticket_id,
                    message=f"Запрос помощи по заявке №{number}: {message}",
                    created_at=now,
                )

            connection.commit()

    def list_comments(self, number: int) -> list[TicketComment]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                return []
            ticket_id = int(row["id"])
            rows = connection.execute(
                "SELECT tc.id, tc.ticket_id, u.username AS author_username, tc.body, tc.created_at "
                "FROM ticket_comments tc "
                "JOIN users u ON u.id = tc.user_id "
                "WHERE tc.ticket_id = ? "
                "ORDER BY tc.id DESC",
                (ticket_id,),
            ).fetchall()
            return [
                TicketComment(
                    id=int(r["id"]),
                    ticket_id=int(r["ticket_id"]),
                    author_username=str(r["author_username"]),
                    body=str(r["body"]),
                    created_at=datetime.fromisoformat(str(r["created_at"])),
                )
                for r in rows
            ]

    def add_comment(self, number: int, *, user_id: int, body: str) -> TicketComment:
        now = utcnow().isoformat()
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                raise KeyError("Request not found")
            ticket_id = int(row["id"])

            cursor = connection.execute(
                "INSERT INTO ticket_comments(ticket_id, user_id, body, created_at) VALUES(?, ?, ?, ?)",
                (ticket_id, user_id, body, now),
            )
            comment_id = int(cursor.lastrowid)
            connection.commit()

            author = connection.execute(
                "SELECT username FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            author_username = str(author["username"]) if author else "unknown"
            return TicketComment(
                id=comment_id,
                ticket_id=ticket_id,
                author_username=author_username,
                body=body,
                created_at=datetime.fromisoformat(now),
            )

    def list_parts(self, number: int) -> list[TicketPart]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                return []
            ticket_id = int(row["id"])
            rows = connection.execute(
                "SELECT id, ticket_id, part_name, quantity, created_at "
                "FROM ticket_parts WHERE ticket_id = ? ORDER BY id DESC",
                (ticket_id,),
            ).fetchall()
            return [
                TicketPart(
                    id=int(r["id"]),
                    ticket_id=int(r["ticket_id"]),
                    part_name=str(r["part_name"]),
                    quantity=int(r["quantity"]),
                    created_at=datetime.fromisoformat(str(r["created_at"])),
                )
                for r in rows
            ]

    def add_part(self, number: int, *, part_name: str, quantity: int) -> TicketPart:
        now = utcnow().isoformat()
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                raise KeyError("Request not found")
            ticket_id = int(row["id"])
            cursor = connection.execute(
                "INSERT INTO ticket_parts(ticket_id, part_name, quantity, created_at) VALUES(?, ?, ?, ?)",
                (ticket_id, part_name, quantity, now),
            )
            part_id = int(cursor.lastrowid)
            connection.commit()
            return TicketPart(
                id=part_id,
                ticket_id=ticket_id,
                part_name=part_name,
                quantity=quantity,
                created_at=datetime.fromisoformat(now),
            )

    def delete_part(self, number: int, part_id: int) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "DELETE FROM ticket_parts WHERE id = ? AND ticket_id = ("
                "SELECT id FROM tickets WHERE request_number = ?"
                ")",
                (part_id, number),
            )
            connection.commit()

    def list_history(self, number: int) -> list[StatusHistoryItem]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT id FROM tickets WHERE request_number = ?",
                (number,),
            ).fetchone()
            if not row:
                return []
            ticket_id = int(row["id"])
            rows = connection.execute(
                "SELECT sh.id, sh.ticket_id, sh.old_status, sh.new_status, u.username AS changed_by, sh.changed_at "
                "FROM status_history sh "
                "JOIN users u ON u.id = sh.changed_by_user_id "
                "WHERE sh.ticket_id = ? "
                "ORDER BY sh.id DESC",
                (ticket_id,),
            ).fetchall()
            items: list[StatusHistoryItem] = []
            for r in rows:
                old_raw = r["old_status"]
                old = RequestStatus(str(old_raw)) if old_raw else None
                items.append(
                    StatusHistoryItem(
                        id=int(r["id"]),
                        ticket_id=int(r["ticket_id"]),
                        old_status=old,
                        new_status=RequestStatus(str(r["new_status"])),
                        changed_by_username=str(r["changed_by"]),
                        changed_at=datetime.fromisoformat(str(r["changed_at"])),
                    )
                )
            return items

    def unread_notifications_count(self, user_id: int) -> int:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
                (user_id,),
            ).fetchone()
            return int(row["c"]) if row else 0

    def list_notifications(self, user_id: int) -> list[NotificationItem]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT n.id, t.request_number AS ticket_number, n.message, n.is_read, n.created_at "
                "FROM notifications n "
                "LEFT JOIN tickets t ON t.id = n.ticket_id "
                "WHERE n.user_id = ? "
                "ORDER BY n.id DESC",
                (user_id,),
            ).fetchall()
            return [
                NotificationItem(
                    id=int(r["id"]),
                    ticket_number=int(r["ticket_number"]) if r["ticket_number"] is not None else None,
                    message=str(r["message"]),
                    is_read=bool(int(r["is_read"])),
                    created_at=datetime.fromisoformat(str(r["created_at"])),
                )
                for r in rows
            ]

    def mark_notification_read(self, user_id: int, notification_id: int) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
                (notification_id, user_id),
            )
            connection.commit()

    def _tickets_select_sql(self) -> str:
        return (
            "SELECT "
            "t.id, t.request_number, t.created_at, t.updated_at, t.status, "
            "c.full_name AS client_name, c.phone AS client_phone, "
            "a.appliance_type, a.appliance_model, "
            "it.name AS issue_type, "
            "t.problem_description, "
            "u.username AS technician_username, "
            "t.due_at, t.started_at, t.completed_at "
            "FROM tickets t "
            "JOIN clients c ON c.id = t.client_id "
            "JOIN appliances a ON a.id = t.appliance_id "
            "LEFT JOIN issue_types it ON it.id = t.issue_type_id "
            "LEFT JOIN users u ON u.id = t.assigned_specialist_id"
        )

    def _row_to_ticket(self, row: sqlite3.Row) -> RepairRequest:
        return RepairRequest(
            id=int(row["id"]),
            number=int(row["request_number"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            due_at=parse_dt(str(row["due_at"]) if row["due_at"] is not None else None),
            appliance_type=str(row["appliance_type"]),
            appliance_model=str(row["appliance_model"]),
            issue_type=str(row["issue_type"]) if row["issue_type"] is not None else None,
            problem_description=str(row["problem_description"]),
            client_name=str(row["client_name"]),
            client_phone=str(row["client_phone"]),
            status=RequestStatus(str(row["status"])),
            technician_username=(
                str(row["technician_username"])
                if row["technician_username"] is not None
                else None
            ),
            started_at=parse_dt(str(row["started_at"]) if row["started_at"] is not None else None),
            completed_at=parse_dt(str(row["completed_at"]) if row["completed_at"] is not None else None),
        )

    def _next_request_number(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT MAX(request_number) AS m FROM tickets").fetchone()
        current = int(row["m"]) if row and row["m"] is not None else 0
        return current + 1

    def _get_or_create_client(
        self, connection: sqlite3.Connection, *, full_name: str, phone: str
    ) -> int:
        existing = connection.execute(
            "SELECT id FROM clients WHERE phone = ?",
            (phone,),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE clients SET full_name = ? WHERE id = ?",
                (full_name, int(existing["id"])),
            )
            return int(existing["id"])

        cursor = connection.execute(
            "INSERT INTO clients(full_name, phone) VALUES(?, ?)",
            (full_name, phone),
        )
        return int(cursor.lastrowid)

    def _get_or_create_appliance(
        self,
        connection: sqlite3.Connection,
        *,
        appliance_type: str,
        appliance_model: str,
    ) -> int:
        existing = connection.execute(
            "SELECT id FROM appliances WHERE appliance_type = ? AND appliance_model = ?",
            (appliance_type, appliance_model),
        ).fetchone()
        if existing:
            return int(existing["id"])

        cursor = connection.execute(
            "INSERT INTO appliances(appliance_type, appliance_model) VALUES(?, ?)",
            (appliance_type, appliance_model),
        )
        return int(cursor.lastrowid)

    def _get_issue_type_id(
        self, connection: sqlite3.Connection, issue_type: str | None
    ) -> int | None:
        if issue_type is None:
            return None
        name = issue_type.strip()
        if not name or name == "Не выбрано":
            return None
        existing = connection.execute(
            "SELECT id FROM issue_types WHERE name = ?",
            (name,),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cursor = connection.execute(
            "INSERT INTO issue_types(name) VALUES(?)",
            (name,),
        )
        return int(cursor.lastrowid)

    def _get_user_id_for_username(
        self, connection: sqlite3.Connection, username: str | None
    ) -> int | None:
        if not username:
            return None
        row = connection.execute(
            "SELECT id FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        return int(row["id"]) if row else None

    def _create_notification(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        ticket_id: int | None,
        message: str,
        created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO notifications(user_id, ticket_id, message, is_read, created_at) "
            "VALUES(?, ?, ?, 0, ?)",
            (user_id, ticket_id, message, created_at),
        )

    def _create_status_change_notifications(
        self,
        connection: sqlite3.Connection,
        *,
        ticket_id: int,
        request_number: int,
        new_status: str,
        changed_by_user_id: int,
        created_at: str,
    ) -> None:
        try:
            label = STATUS_LABELS[RequestStatus(new_status)]
        except Exception:
            label = new_status
        rows = connection.execute(
            "SELECT id FROM users WHERE is_active = 1 AND role IN (?, ?, ?) AND id != ?",
            (Role.ADMIN.value, Role.OPERATOR.value, Role.MANAGER.value, changed_by_user_id),
        ).fetchall()
        for r in rows:
            self._create_notification(
                connection,
                user_id=int(r["id"]),
                ticket_id=ticket_id,
                message=f"Заявка №{request_number}: статус изменён на «{label}».",
                created_at=created_at,
            )
