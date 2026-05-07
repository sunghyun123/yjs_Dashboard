# app/db/repos/admin.py
from typing import Any, Dict, List, Optional

from app.db.connection import get_conn


class AdminRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def create_request(self, request_type: str, source_category: str, request_text: str,
                       summary: str, payload_json: str = "", requested_by: str = "") -> int:
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO admin_requests (request_type, source_category, request_text, summary, payload_json, requested_by) VALUES (?,?,?,?,?,?)",
                    (request_type, source_category, request_text, summary, payload_json, requested_by),
                )
                return int(cursor.lastrowid)

    def list_requests(self, status: str = "pending", requested_by: Optional[str] = None,
                      since: Optional[str] = None, until: Optional[str] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT id, request_type, source_category, request_text, summary, payload_json,
                   requested_by, status, datetime(created_at,'localtime') AS created_at
            FROM admin_requests WHERE status=?
        """
        params: List[Any] = [status]
        if requested_by and requested_by.strip():
            query += " AND requested_by LIKE ?"
            params.append(f"%{requested_by.strip()}%")
        if since and since.strip():
            query += " AND date(datetime(created_at,'localtime')) >= date(?)"
            params.append(since.strip()[:10])
        if until and until.strip():
            query += " AND date(datetime(created_at,'localtime')) <= date(?)"
            params.append(until.strip()[:10])
        query += " ORDER BY id DESC LIMIT 200"
        with get_conn(self._db_path) as conn:
            return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]

    def get_request_by_id(self, request_id: int) -> Optional[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            row = conn.execute("SELECT * FROM admin_requests WHERE id=?", (request_id,)).fetchone()
            return dict(row) if row else None

    def update_request_status(self, request_id: int, status: str) -> None:
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute("UPDATE admin_requests SET status=? WHERE id=?", (status, request_id))

    def create_audit_event(self, entity_type: str, entity_id: Optional[int], action: str,
                           before_json: str = "", after_json: str = "", reason: str = "",
                           actor_user: str = "", actor_device: str = "") -> int:
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO audit_events (entity_type, entity_id, action, before_json, after_json, reason, actor_user, actor_device) VALUES (?,?,?,?,?,?,?,?)",
                    (entity_type, entity_id, action, before_json, after_json, reason, actor_user, actor_device),
                )
                return int(cursor.lastrowid)

    def list_audit_events(self, limit: int = 200, actions: Optional[List[str]] = None,
                          since: Optional[str] = None, until: Optional[str] = None) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        query = """
            SELECT id, entity_type, entity_id, action, before_json, after_json, reason,
                   actor_user, actor_device, datetime(created_at,'localtime') AS created_at
            FROM audit_events
        """
        where_parts: List[str] = []
        params: List[Any] = []
        if actions:
            placeholders = ",".join(["?"] * len(actions))
            where_parts.append(f"action IN ({placeholders})")
            params.extend(actions)
        if since and since.strip():
            where_parts.append("date(datetime(created_at,'localtime')) >= date(?)")
            params.append(since.strip()[:10])
        if until and until.strip():
            where_parts.append("date(datetime(created_at,'localtime')) <= date(?)")
            params.append(until.strip()[:10])
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(safe_limit)
        with get_conn(self._db_path) as conn:
            return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]

    def log_chat_event(self, user_id: str, input_category: str, message_text: str,
                       intent: str = "", response_status: str = "success") -> int:
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO chat_events (user_id, input_category, intent, message_text, response_status) VALUES (?,?,?,?,?)",
                    (
                        (user_id or "").strip(),
                        (input_category or "").strip(),
                        (intent or "").strip(),
                        (message_text or "").strip(),
                        (response_status or "success").strip(),
                    ),
                )
                return int(cursor.lastrowid)

    def list_daily_requests(self, target_date: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, request_type, source_category, request_text, summary, payload_json, requested_by, status, datetime(created_at,'localtime') AS created_at FROM admin_requests WHERE date(datetime(created_at,'localtime'))=? ORDER BY created_at DESC",
                (target_date,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_daily_audit_events(self, target_date: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, entity_type, entity_id, action, reason, actor_user, actor_device, datetime(created_at,'localtime') AS created_at FROM audit_events WHERE date(datetime(created_at,'localtime'))=? ORDER BY created_at DESC",
                (target_date,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_daily_chat_events(self, target_date: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, user_id, input_category, intent, message_text, response_status, datetime(created_at,'localtime') AS created_at FROM chat_events WHERE date(datetime(created_at,'localtime'))=? ORDER BY created_at DESC",
                (target_date,),
            ).fetchall()
            return [dict(r) for r in rows]
