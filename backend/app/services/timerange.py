from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


def resolve_range(hours: int, date: str | None) -> tuple[datetime, datetime | None]:
    """Shared by every "history" endpoint (tracker positions, telemetry,
    device locations): either a rolling window ("last N hours") or one
    specific calendar day ("YYYY-MM-DD", UTC) for browsing day-by-day
    further back than the rolling window covers.

    Returns (since, until) — until is None to mean "no upper bound (now)".
    """
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_date")
        return day, day + timedelta(days=1)
    return datetime.now(timezone.utc) - timedelta(hours=hours), None
