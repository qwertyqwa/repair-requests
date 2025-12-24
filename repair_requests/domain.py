from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    MASTER = "master"
    MANAGER = "manager"


class RequestStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    AWAITING_PARTS = "awaiting_parts"
    READY = "ready"


STATUS_LABELS: dict[RequestStatus, str] = {
    RequestStatus.NEW: "Новая",
    RequestStatus.IN_PROGRESS: "В ремонте",
    RequestStatus.AWAITING_PARTS: "Ожидание запчастей",
    RequestStatus.READY: "Готова к выдаче",
}


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Администратор",
    Role.OPERATOR: "Оператор",
    Role.MASTER: "Мастер",
    Role.MANAGER: "Менеджер по качеству",
}


ISSUE_TYPES: list[str] = [
    "Не выбрано",
    "Электрика",
    "Механика",
    "Протечка/вода",
    "Перегрев",
    "Шум/вибрация",
    "Другое",
]


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    role: Role
    full_name: str = ""
    is_active: bool = True

@dataclass(frozen=True)
class RepairRequest:
    id: int
    number: int
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None
    appliance_type: str
    appliance_model: str
    issue_type: str | None
    problem_description: str
    client_name: str
    client_phone: str
    status: RequestStatus
    technician_username: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

@dataclass(frozen=True)
class TicketComment:
    id: int
    ticket_id: int
    author_username: str
    body: str
    created_at: datetime


@dataclass(frozen=True)
class TicketPart:
    id: int
    ticket_id: int
    part_name: str
    quantity: int
    created_at: datetime


@dataclass(frozen=True)
class StatusHistoryItem:
    id: int
    ticket_id: int
    old_status: RequestStatus | None
    new_status: RequestStatus
    changed_by_username: str
    changed_at: datetime


@dataclass(frozen=True)
class NotificationItem:
    id: int
    ticket_number: int | None
    message: str
    is_read: bool
    created_at: datetime
