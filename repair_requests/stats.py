from __future__ import annotations

from collections import Counter
from datetime import timedelta

from repair_requests.domain import RepairRequest, RequestStatus


def request_repair_duration(request: RepairRequest) -> timedelta | None:
    if request.completed_at is None:
        return None
    start = request.started_at or request.created_at
    if request.completed_at < start:
        return None
    return request.completed_at - start


def average_repair_time(requests: list[RepairRequest]) -> timedelta | None:
    durations: list[timedelta] = []
    for request in requests:
        duration = request_repair_duration(request)
        if duration is None:
            continue
        durations.append(duration)
    if not durations:
        return None
    total = timedelta()
    for duration in durations:
        total += duration
    return total / len(durations)


def requests_summary(requests: list[RepairRequest]) -> dict[str, object]:
    completed = [r for r in requests if r.status == RequestStatus.READY]
    avg = average_repair_time(completed)
    issue_counter = Counter()
    for request in requests:
        issue = (request.issue_type or "").strip()
        if not issue:
            issue = "Не указано"
        issue_counter[issue] += 1

    return {
        "total": len(requests),
        "completed": len(completed),
        "average_repair_time": avg,
        "by_issue_type": issue_counter.most_common(),
    }


def format_timedelta(value: timedelta | None) -> str:
    if value is None:
        return "—"
    seconds = int(value.total_seconds())
    if seconds < 0:
        return "—"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} д")
    if hours or days:
        parts.append(f"{hours} ч")
    parts.append(f"{minutes} мин")
    return " ".join(parts)

