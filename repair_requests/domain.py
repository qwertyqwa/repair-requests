from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    MASTER = "master"


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
    username: str
    password_hash: str
    role: Role
    full_name: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role.value,
            "full_name": self.full_name,
        }

    @staticmethod
    def from_dict(data: dict[str, str]) -> "User":
        return User(
            username=data["username"],
            password_hash=data["password_hash"],
            role=Role(data["role"]),
            full_name=data.get("full_name", ""),
        )


@dataclass
class RepairRequest:
    number: int
    created_at: datetime
    appliance_type: str
    appliance_model: str
    issue_type: str
    problem_description: str
    client_name: str
    client_phone: str
    status: RequestStatus = RequestStatus.NEW
    technician_username: str | None = None
    master_notes: str = ""
    parts_notes: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "created_at": self.created_at.isoformat(),
            "appliance_type": self.appliance_type,
            "appliance_model": self.appliance_model,
            "issue_type": self.issue_type,
            "problem_description": self.problem_description,
            "client_name": self.client_name,
            "client_phone": self.client_phone,
            "status": self.status.value,
            "technician_username": self.technician_username,
            "master_notes": self.master_notes,
            "parts_notes": self.parts_notes,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict[str, object]) -> "RepairRequest":
        def parse_dt(value: object) -> datetime | None:
            if not value:
                return None
            if not isinstance(value, str):
                raise ValueError("Invalid datetime value")
            return datetime.fromisoformat(value)

        created_at_raw = data["created_at"]
        if not isinstance(created_at_raw, str):
            raise ValueError("Invalid created_at")

        updated_at_raw = data.get("updated_at")
        if updated_at_raw is not None and not isinstance(updated_at_raw, str):
            raise ValueError("Invalid updated_at")

        return RepairRequest(
            number=int(data["number"]),
            created_at=datetime.fromisoformat(created_at_raw),
            appliance_type=str(data.get("appliance_type", "")),
            appliance_model=str(data.get("appliance_model", "")),
            issue_type=str(data.get("issue_type", "")),
            problem_description=str(data.get("problem_description", "")),
            client_name=str(data.get("client_name", "")),
            client_phone=str(data.get("client_phone", "")),
            status=RequestStatus(str(data.get("status", RequestStatus.NEW.value))),
            technician_username=(
                str(data.get("technician_username"))
                if data.get("technician_username") is not None
                else None
            ),
            master_notes=str(data.get("master_notes", "")),
            parts_notes=str(data.get("parts_notes", "")),
            started_at=parse_dt(data.get("started_at")),
            completed_at=parse_dt(data.get("completed_at")),
            updated_at=(
                datetime.fromisoformat(updated_at_raw)
                if isinstance(updated_at_raw, str)
                else utcnow()
            ),
        )

