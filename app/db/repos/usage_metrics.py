from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from app.db.connection import get_conn


SCHEDULE_EVENT_TYPES = {
    "schedule_created",
    "schedule_updated",
    "schedule_deleted",
}


class UsageMetricsRepository:
    """Append-only usage events and management-facing aggregates."""

    def __init__(self, db_path: str, timezone_name: str = "Asia/Seoul"):
        self._db_path = db_path
        try:
            self._timezone = ZoneInfo(timezone_name)
        except Exception:
            self._timezone = timezone.utc

    def _now_values(self) -> tuple[str, str]:
        now_utc = datetime.now(timezone.utc)
        activity_date = now_utc.astimezone(self._timezone).date().isoformat()
        return activity_date, now_utc.isoformat()

    def record_user_activity(self, actor_user: str, actor_device: str = "", source: str = "auth_me") -> None:
        """Record at most one page-level active event per user and local calendar day."""
        user = str(actor_user or "").strip()
        if not user:
            return
        activity_date, occurred_at = self._now_values()
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO usage_events
                        (event_type, actor_user, actor_device, entity_type, entity_id,
                         source, activity_date, occurred_at)
                    VALUES ('user_active', ?, ?, '', NULL, ?, ?, ?)
                    """,
                    (user, str(actor_device or ""), str(source or ""), activity_date, occurred_at),
                )

    def record_schedule_event(
        self,
        event_type: str,
        actor_user: str,
        actor_device: str = "",
        schedule_id: Optional[int] = None,
        source: str = "",
    ) -> None:
        self.record_schedule_events(
            event_type=event_type,
            actor_user=actor_user,
            actor_device=actor_device,
            schedule_ids=[schedule_id],
            source=source,
        )

    def record_schedule_events(
        self,
        event_type: str,
        actor_user: str,
        actor_device: str = "",
        schedule_ids: Iterable[Optional[int]] = (),
        source: str = "",
    ) -> None:
        if event_type not in SCHEDULE_EVENT_TYPES:
            raise ValueError("지원하지 않는 일정 이벤트 유형입니다.")
        ids = list(schedule_ids)
        if not ids:
            return
        activity_date, occurred_at = self._now_values()
        rows = [
            (
                event_type,
                str(actor_user or "").strip(),
                str(actor_device or ""),
                "field_schedules",
                int(schedule_id) if schedule_id is not None else None,
                str(source or ""),
                activity_date,
                occurred_at,
            )
            for schedule_id in ids
        ]
        with get_conn(self._db_path) as conn:
            with conn:
                conn.executemany(
                    """
                    INSERT INTO usage_events
                        (event_type, actor_user, actor_device, entity_type, entity_id,
                         source, activity_date, occurred_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    rows,
                )

    def get_usage_metrics(self, date_from: str, date_to: str) -> Dict[str, Any]:
        human_actor = "TRIM(COALESCE(actor_user,'')) <> '' AND actor_user NOT IN ('auto-system','system')"
        week_start = (
            "date(activity_date, '-' || "
            "((CAST(strftime('%w', activity_date) AS INTEGER) + 6) % 7) || ' days')"
        )

        with get_conn(self._db_path) as conn:
            summary_row = conn.execute(
                f"""
                SELECT
                    COUNT(DISTINCT CASE WHEN {human_actor} THEN actor_user END) AS active_users,
                    COUNT(DISTINCT CASE WHEN {human_actor} THEN activity_date END) AS activity_days,
                    SUM(CASE WHEN event_type='schedule_created' THEN 1 ELSE 0 END) AS schedule_created_count,
                    SUM(CASE WHEN event_type='schedule_updated' THEN 1 ELSE 0 END) AS schedule_update_count,
                    SUM(CASE WHEN event_type='schedule_deleted' THEN 1 ELSE 0 END) AS schedule_delete_count
                FROM usage_events
                WHERE activity_date BETWEEN ? AND ?
                """,
                (date_from, date_to),
            ).fetchone()

            daily_rows = conn.execute(
                f"""
                SELECT
                    activity_date AS date,
                    COUNT(DISTINCT CASE WHEN {human_actor} THEN actor_user END) AS active_users,
                    SUM(CASE WHEN event_type='schedule_created' THEN 1 ELSE 0 END) AS schedule_created_count,
                    SUM(CASE WHEN event_type='schedule_updated' THEN 1 ELSE 0 END) AS schedule_update_count,
                    SUM(CASE WHEN event_type='schedule_deleted' THEN 1 ELSE 0 END) AS schedule_delete_count
                FROM usage_events
                WHERE activity_date BETWEEN ? AND ?
                GROUP BY activity_date
                ORDER BY activity_date
                """,
                (date_from, date_to),
            ).fetchall()

            weekly_rows = conn.execute(
                f"""
                SELECT
                    {week_start} AS week_start,
                    date({week_start}, '+6 days') AS week_end,
                    COUNT(DISTINCT CASE WHEN {human_actor} THEN actor_user END) AS weekly_active_users,
                    COUNT(DISTINCT CASE WHEN {human_actor} THEN activity_date END) AS activity_days,
                    SUM(CASE WHEN event_type='schedule_created' THEN 1 ELSE 0 END) AS schedule_created_count,
                    SUM(CASE WHEN event_type='schedule_updated' THEN 1 ELSE 0 END) AS schedule_update_count,
                    SUM(CASE WHEN event_type='schedule_deleted' THEN 1 ELSE 0 END) AS schedule_delete_count
                FROM usage_events
                WHERE activity_date BETWEEN ? AND ?
                GROUP BY {week_start}
                ORDER BY {week_start}
                """,
                (date_from, date_to),
            ).fetchall()

            availability = conn.execute(
                "SELECT MIN(activity_date) AS data_available_from FROM usage_events"
            ).fetchone()

        def numeric_row(row: Any) -> Dict[str, Any]:
            item = dict(row)
            for key, value in list(item.items()):
                if key not in {"date", "week_start", "week_end"}:
                    item[key] = int(value or 0)
            return item

        return {
            "data_available_from": availability["data_available_from"] if availability else None,
            "summary": numeric_row(summary_row),
            "daily": [numeric_row(row) for row in daily_rows],
            "weekly": [numeric_row(row) for row in weekly_rows],
        }
