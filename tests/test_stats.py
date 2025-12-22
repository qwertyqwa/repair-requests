from __future__ import annotations

from datetime import datetime, timezone

from repair_requests.domain import RepairRequest, RequestStatus
from repair_requests.stats import average_repair_time


def test_average_repair_time_calculates_mean_duration():
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    r1 = RepairRequest(
        number=1,
        created_at=base,
        appliance_type="Холодильник",
        appliance_model="LG",
        issue_type="Электрика",
        problem_description="Не включается",
        client_name="Иванов И.И.",
        client_phone="89991234567",
        status=RequestStatus.READY,
        started_at=base,
        completed_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    r2 = RepairRequest(
        number=2,
        created_at=base,
        appliance_type="Стиральная машина",
        appliance_model="Samsung",
        issue_type="Механика",
        problem_description="Не отжимает",
        client_name="Петров П.П.",
        client_phone="89990000000",
        status=RequestStatus.READY,
        started_at=base,
        completed_at=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
    )

    avg = average_repair_time([r1, r2])
    assert avg is not None
    assert avg.total_seconds() == 3 * 3600

