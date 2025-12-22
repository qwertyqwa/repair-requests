from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from repair_requests.domain import RepairRequest, RequestStatus, Role, User, utcnow


class JsonStore:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self._users: dict[str, User] = {}
        self._requests: dict[int, RepairRequest] = {}
        self._next_request_number = 1

    @property
    def users_path(self) -> Path:
        return self.data_dir / "users.json"

    @property
    def requests_path(self) -> Path:
        return self.data_dir / "requests.json"

    def bootstrap(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.users_path.exists():
            self._bootstrap_users()
        if not self.requests_path.exists():
            self._bootstrap_requests()
        self._load()

    def verify_password(self, username: str, password: str) -> bool:
        user = self._users.get(username)
        if not user:
            return False
        return check_password_hash(user.password_hash, password)

    def get_user(self, username: str) -> User | None:
        return self._users.get(username)

    def list_masters(self) -> list[User]:
        return sorted(
            [u for u in self._users.values() if u.role == Role.MASTER],
            key=lambda u: u.username.lower(),
        )

    def list_requests(self) -> list[RepairRequest]:
        return sorted(self._requests.values(), key=lambda r: r.number, reverse=True)

    def get_request(self, number: int) -> RepairRequest | None:
        return self._requests.get(number)

    def create_request(
        self,
        *,
        appliance_type: str,
        appliance_model: str,
        issue_type: str,
        problem_description: str,
        client_name: str,
        client_phone: str,
    ) -> RepairRequest:
        number = self._next_request_number
        self._next_request_number += 1

        request = RepairRequest(
            number=number,
            created_at=utcnow(),
            appliance_type=appliance_type,
            appliance_model=appliance_model,
            issue_type=issue_type,
            problem_description=problem_description,
            client_name=client_name,
            client_phone=client_phone,
        )
        self._requests[number] = request
        self._save()
        return request

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
        master_notes: str | None = None,
        parts_notes: str | None = None,
    ) -> RepairRequest:
        existing = self._requests.get(number)
        if not existing:
            raise KeyError("Request not found")

        updated = replace(existing)
        if appliance_type is not None:
            updated.appliance_type = appliance_type
        if appliance_model is not None:
            updated.appliance_model = appliance_model
        if issue_type is not None:
            updated.issue_type = issue_type
        if problem_description is not None:
            updated.problem_description = problem_description
        if client_name is not None:
            updated.client_name = client_name
        if client_phone is not None:
            updated.client_phone = client_phone
        if technician_username is not None:
            updated.technician_username = technician_username or None
        if master_notes is not None:
            updated.master_notes = master_notes
        if parts_notes is not None:
            updated.parts_notes = parts_notes

        if status is not None and status != updated.status:
            updated = self._apply_status_transition(updated, status)

        updated.updated_at = utcnow()
        self._requests[number] = updated
        self._save()
        return updated

    def delete_request(self, number: int) -> None:
        if number in self._requests:
            del self._requests[number]
            self._save()

    def search_requests(
        self,
        *,
        query: str,
        status: RequestStatus | None = None,
        technician_username: str | None = None,
    ) -> list[RepairRequest]:
        needle = query.strip().lower()
        results: list[RepairRequest] = []
        for request in self._requests.values():
            if status is not None and request.status != status:
                continue
            if technician_username is not None and request.technician_username != technician_username:
                continue
            if not needle:
                results.append(request)
                continue

            haystack = " ".join(
                [
                    str(request.number),
                    request.appliance_type,
                    request.appliance_model,
                    request.issue_type,
                    request.problem_description,
                    request.client_name,
                    request.client_phone,
                    request.status.value,
                    request.technician_username or "",
                ]
            ).lower()
            if needle in haystack:
                results.append(request)

        return sorted(results, key=lambda r: r.number, reverse=True)

    def _apply_status_transition(
        self, request: RepairRequest, next_status: RequestStatus
    ) -> RepairRequest:
        if next_status == RequestStatus.IN_PROGRESS and request.started_at is None:
            request.started_at = utcnow()
        if next_status == RequestStatus.READY and request.completed_at is None:
            request.completed_at = utcnow()
        request.status = next_status
        return request

    def _bootstrap_users(self) -> None:
        default_users = [
            User(
                username="admin",
                password_hash=generate_password_hash("admin"),
                role=Role.ADMIN,
                full_name="Администратор",
            ),
            User(
                username="operator",
                password_hash=generate_password_hash("operator"),
                role=Role.OPERATOR,
                full_name="Оператор",
            ),
            User(
                username="master",
                password_hash=generate_password_hash("master"),
                role=Role.MASTER,
                full_name="Мастер",
            ),
        ]
        payload = {"users": [u.to_dict() for u in default_users]}
        self._atomic_write_json(self.users_path, payload)

    def _bootstrap_requests(self) -> None:
        payload = {"next_number": 1, "requests": []}
        self._atomic_write_json(self.requests_path, payload)

    def _load(self) -> None:
        users_payload = self._read_json(self.users_path)
        users_raw = users_payload.get("users", [])
        if not isinstance(users_raw, list):
            raise ValueError("Invalid users.json format")
        self._users = {}
        for item in users_raw:
            if not isinstance(item, dict):
                continue
            user = User.from_dict(item)  # type: ignore[arg-type]
            self._users[user.username] = user

        requests_payload = self._read_json(self.requests_path)
        next_number = requests_payload.get("next_number", 1)
        if not isinstance(next_number, int):
            raise ValueError("Invalid next_number")
        self._next_request_number = max(1, next_number)

        requests_raw = requests_payload.get("requests", [])
        if not isinstance(requests_raw, list):
            raise ValueError("Invalid requests.json format")
        self._requests = {}
        for item in requests_raw:
            if not isinstance(item, dict):
                continue
            request = RepairRequest.from_dict(item)
            self._requests[request.number] = request
            self._next_request_number = max(self._next_request_number, request.number + 1)

    def _save(self) -> None:
        payload = {
            "next_number": self._next_request_number,
            "requests": [r.to_dict() for r in self.list_requests()[::-1]],
        }
        self._atomic_write_json(self.requests_path, payload)

    def _read_json(self, path: Path) -> dict[str, Any]:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid JSON root")
        return data

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)
