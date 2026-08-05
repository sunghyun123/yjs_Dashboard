import sqlite3

from app.db.migrations import run_migrations
from app.db.repos.export import ExportRepository
from app.db.repos.usage_metrics import UsageMetricsRepository


def test_usage_metrics_group_by_monday_week_and_distinct_users(tmp_path):
    db_path = str(tmp_path / "usage_metrics.db")
    run_migrations(db_path)
    rows = [
        ("user_active", "user-1", "2026-08-03"),
        ("user_active", "user-1", "2026-08-04"),
        ("schedule_created", "user-1", "2026-08-04"),
        ("user_active", "user-2", "2026-08-05"),
        ("schedule_updated", "user-2", "2026-08-05"),
        ("user_active", "auto-system", "2026-08-06"),
        ("user_active", "user-2", "2026-08-10"),
        ("schedule_deleted", "user-2", "2026-08-10"),
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO usage_events
                (event_type, actor_user, actor_device, entity_type, entity_id,
                 source, activity_date, occurred_at)
            VALUES (?, ?, '', '', NULL, 'test', ?, ? || 'T00:00:00+00:00')
            """,
            [(event_type, actor_user, activity_date, activity_date) for event_type, actor_user, activity_date in rows],
        )

    metrics = UsageMetricsRepository(db_path).get_usage_metrics("2026-08-03", "2026-08-16")

    assert metrics["summary"] == {
        "active_users": 2,
        "activity_days": 4,
        "schedule_created_count": 1,
        "schedule_update_count": 1,
        "schedule_delete_count": 1,
    }
    assert metrics["weekly"] == [
        {
            "week_start": "2026-08-03",
            "week_end": "2026-08-09",
            "weekly_active_users": 2,
            "activity_days": 3,
            "schedule_created_count": 1,
            "schedule_update_count": 1,
            "schedule_delete_count": 0,
        },
        {
            "week_start": "2026-08-10",
            "week_end": "2026-08-16",
            "weekly_active_users": 1,
            "activity_days": 1,
            "schedule_created_count": 0,
            "schedule_update_count": 0,
            "schedule_delete_count": 1,
        },
    ]

    daily_export_metrics = ExportRepository(db_path).get_daily_metrics("2026-08-05")
    assert daily_export_metrics["daily_active_user_count"] == 1
    assert daily_export_metrics["schedule_created_count"] == 0
    assert daily_export_metrics["schedule_update_count"] == 1
    assert daily_export_metrics["schedule_delete_count"] == 0
