# app/db/repos/export.py
from typing import Any, Dict, List, Optional

from app.db.connection import get_conn


class ExportRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def create_export_job(self, target_date: str, status: str, output_path: str = "", message: str = "") -> int:
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO export_jobs (target_date, status, output_path, message) VALUES (?,?,?,?)",
                    (target_date, status, output_path, message),
                )
                return int(cursor.lastrowid)

    def has_success_export(self, target_date: str) -> bool:
        with get_conn(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM export_jobs WHERE target_date=? AND status='success' LIMIT 1",
                (target_date,),
            ).fetchone()
            return bool(row)

    def save_photo_upload(self, category: str, file_path: str, uploaded_by: str, uploaded_device: str,
                          related_date: str, file_size: int = 0, file_sha256: str = "",
                          linked_schedule_id: Optional[int] = None, note: str = "") -> int:
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO photo_uploads (category, file_path, uploaded_by, uploaded_device, related_date, file_size, file_sha256, linked_schedule_id, note) VALUES (?,?,?,?,?,?,?,?,?)",
                    (category, file_path, uploaded_by, uploaded_device, related_date,
                     int(file_size or 0), str(file_sha256 or ""), linked_schedule_id, str(note or "")),
                )
                return int(cursor.lastrowid)

    def get_schedule_attachments(self, schedule_id: int) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, category, file_path, uploaded_by, related_date, note, datetime(created_at,'localtime') as created_at FROM photo_uploads WHERE linked_schedule_id=? ORDER BY created_at ASC",
                (schedule_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_schedule_attachment(self, attachment_id: int, schedule_id: int) -> bool:
        with get_conn(self._db_path) as conn:
            with conn:
                row = conn.execute(
                    "SELECT file_path FROM photo_uploads WHERE id=? AND linked_schedule_id=?",
                    (attachment_id, schedule_id),
                ).fetchone()
                if not row:
                    return False
                conn.execute("DELETE FROM photo_uploads WHERE id=?", (attachment_id,))
                return True

    def list_daily_photo_uploads(self, target_date: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, category, file_path, uploaded_by, uploaded_device, related_date, datetime(created_at,'localtime') AS created_at FROM photo_uploads WHERE related_date=? OR date(datetime(created_at,'localtime'))=? ORDER BY created_at DESC",
                (target_date, target_date),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_daily_metrics(self, target_date: str) -> Dict[str, Any]:
        with get_conn(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM field_schedules WHERE date=? AND deleted_at IS NULL) AS active_schedule_count,
                    (SELECT COUNT(*) FROM field_schedules WHERE date(datetime(created_at,'localtime'))=?) AS schedule_created_count,
                    (SELECT COUNT(*) FROM worker_status) AS outing_status_snapshot_count,
                    (SELECT COUNT(*) FROM admin_requests WHERE date(datetime(created_at,'localtime'))=?) AS admin_request_count,
                    (SELECT COUNT(*) FROM photo_uploads WHERE related_date=? OR date(datetime(created_at,'localtime'))=?) AS photo_upload_count,
                    (SELECT COUNT(*) FROM audit_events WHERE date(datetime(created_at,'localtime'))=?) AS audit_event_count,
                    (SELECT COUNT(*) FROM sessions WHERE date(datetime(created_at,'localtime'))=?) AS login_session_count,
                    (SELECT COUNT(*) FROM chat_events WHERE date(datetime(created_at,'localtime'))=?) AS chat_count,
                    (SELECT COUNT(*) FROM audit_events WHERE entity_type='schedule' AND action='update' AND date(datetime(created_at,'localtime'))=?) AS schedule_update_count,
                    (SELECT COUNT(*) FROM audit_events WHERE entity_type='schedule' AND action='delete' AND date(datetime(created_at,'localtime'))=?) AS schedule_delete_count
                """,
                (target_date, target_date, target_date, target_date, target_date,
                 target_date, target_date, target_date, target_date, target_date),
            ).fetchone()
            metrics = dict(row) if row else {}

            active_users_rows = conn.execute(
                """
                SELECT DISTINCT actor_user AS user_name FROM (
                    SELECT COALESCE(last_actor_user,'') AS actor_user FROM field_schedules WHERE date(last_actor_at)=?
                    UNION ALL
                    SELECT COALESCE(requested_by,'') FROM admin_requests WHERE date(datetime(created_at,'localtime'))=?
                    UNION ALL
                    SELECT COALESCE(uploaded_by,'') FROM photo_uploads WHERE related_date=? OR date(datetime(created_at,'localtime'))=?
                    UNION ALL
                    SELECT COALESCE(actor_user,'') FROM audit_events WHERE date(datetime(created_at,'localtime'))=?
                    UNION ALL
                    SELECT COALESCE(user_id,'') FROM sessions WHERE date(datetime(created_at,'localtime'))=?
                    UNION ALL
                    SELECT COALESCE(user_id,'') FROM chat_events WHERE date(datetime(created_at,'localtime'))=?
                ) WHERE user_name != ''
                """,
                (target_date, target_date, target_date, target_date, target_date, target_date, target_date),
            ).fetchall()
            metrics["target_date"] = target_date
            metrics["daily_active_user_count"] = len(active_users_rows)
            return {k: int(v) if isinstance(v, int) and k != "target_date" else v for k, v in metrics.items()}
