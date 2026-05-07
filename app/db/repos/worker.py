# app/db/repos/worker.py
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.db.connection import get_conn

logger = logging.getLogger(__name__)


def _parse_local_datetime(value: str) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


class WorkerRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def upsert_status(self, user_name: str, status: str, location: str = "", until_time: str = "",
                      note: str = "", actor_user: str = "", actor_device: str = "") -> None:
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO worker_status
                    (user_name, status, location, until_time, note, updated_at, last_actor_user, last_actor_device, last_actor_at)
                    VALUES (?,?,?,?,?,CURRENT_TIMESTAMP,?,?,?)
                    ON CONFLICT(user_name) DO UPDATE SET
                        status=excluded.status, location=excluded.location, until_time=excluded.until_time,
                        note=excluded.note, updated_at=CURRENT_TIMESTAMP,
                        last_actor_user=excluded.last_actor_user, last_actor_device=excluded.last_actor_device,
                        last_actor_at=excluded.last_actor_at
                    """,
                    (user_name, status, location, until_time, note, actor_user, actor_device, datetime.utcnow().isoformat()),
                )

    def _apply_outing_auto_return(self, tz_name: str = "Asia/Seoul") -> int:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Seoul")
        now_z = datetime.now(tz)
        expired_users: List[str] = []
        with get_conn(self._db_path) as conn:
            with conn:
                rows = conn.execute(
                    "SELECT user_name, until_time FROM worker_status WHERE status='외출' AND until_time IS NOT NULL AND until_time != ''",
                ).fetchall()
                for row in rows:
                    naive = _parse_local_datetime(row["until_time"])
                    if naive is None:
                        continue
                    try:
                        until_z = naive.replace(tzinfo=tz)
                    except Exception:
                        continue
                    if until_z <= now_z:
                        expired_users.append(str(row["user_name"]))
                if not expired_users:
                    return 0
                placeholders = ",".join(["?"] * len(expired_users))
                now_iso = datetime.utcnow().isoformat()
                cursor = conn.execute(
                    f"""
                    UPDATE worker_status
                    SET status='사무실', location='', until_time='', note='', updated_at=CURRENT_TIMESTAMP,
                        last_actor_user='auto-system', last_actor_device='auto-system', last_actor_at=?
                    WHERE user_name IN ({placeholders})
                    """,
                    (now_iso, *expired_users),
                )
                n = int(cursor.rowcount or 0)

        if n > 0:
            try:
                from app.db.repos.admin import AdminRepository
                AdminRepository(self._db_path).create_audit_event(
                    entity_type="worker_status",
                    entity_id=None,
                    action="outing_auto_return",
                    before_json=json.dumps({"users": expired_users}, ensure_ascii=False),
                    after_json=json.dumps({"status": "사무실", "count": n}, ensure_ascii=False),
                    reason="until_time 경과 자동 사무실 복귀",
                    actor_user="auto-system",
                    actor_device="auto-system",
                )
            except Exception as ex:
                logger.warning("outing_auto_return audit 로그 실패(무시): %s", ex)
        return n

    def list_status(self, tz_name: str = "Asia/Seoul") -> List[Dict[str, Any]]:
        self._apply_outing_auto_return(tz_name)
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT user_name, status, location, until_time, note,
                       datetime(updated_at,'localtime') AS updated_at,
                       last_actor_user, last_actor_device, last_actor_at
                FROM worker_status
                ORDER BY CASE status WHEN '외출' THEN 1 WHEN '사무실' THEN 2 WHEN '야간작업' THEN 3 WHEN '휴가' THEN 4 ELSE 9 END ASC,
                         updated_at DESC, user_name ASC
                """,
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_status(self, user_name: str) -> bool:
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM worker_status WHERE user_name=?", (user_name,))
                return cursor.rowcount > 0

    def list_field_staff(self) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            return [dict(r) for r in conn.execute("SELECT id, name, sort_order FROM field_staff ORDER BY sort_order ASC, name ASC").fetchall()]

    def add_field_staff(self, name: str, sort_order: int = 0) -> int:
        n = (name or "").strip()
        if not n:
            raise ValueError("이름이 필요합니다.")
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute("INSERT INTO field_staff (name, sort_order) VALUES (?,?)", (n, sort_order))
                return int(cursor.lastrowid)

    def delete_field_staff(self, staff_id: int) -> bool:
        with get_conn(self._db_path) as conn:
            with conn:
                return conn.execute("DELETE FROM field_staff WHERE id=?", (staff_id,)).rowcount > 0

    def list_outing_staff(self) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            return [dict(r) for r in conn.execute("SELECT id, name, sort_order FROM outing_staff ORDER BY sort_order ASC, id ASC").fetchall()]

    def add_outing_staff(self, name: str, sort_order: int = 0) -> int:
        n = (name or "").strip()
        if not n:
            raise ValueError("이름이 필요합니다.")
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute("INSERT INTO outing_staff (name, sort_order) VALUES (?,?)", (n, sort_order))
                return int(cursor.lastrowid)

    def delete_outing_staff(self, staff_id: int) -> bool:
        with get_conn(self._db_path) as conn:
            with conn:
                return conn.execute("DELETE FROM outing_staff WHERE id=?", (staff_id,)).rowcount > 0

    def list_frequent_sites(self) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            return [dict(r) for r in conn.execute("SELECT id, title, url, sort_order FROM frequent_sites ORDER BY sort_order ASC, id ASC").fetchall()]

    def add_frequent_site(self, title: str, url: str, sort_order: int = 0) -> int:
        t = (title or "").strip()
        u = (url or "").strip()
        if not t:
            raise ValueError("사이트 이름이 필요합니다.")
        if not u:
            raise ValueError("사이트 URL이 필요합니다.")
        if not (u.startswith("http://") or u.startswith("https://")):
            raise ValueError("URL은 http:// 또는 https:// 로 시작해야 합니다.")
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute("INSERT INTO frequent_sites (title, url, sort_order) VALUES (?,?,?)", (t, u, sort_order))
                return int(cursor.lastrowid)

    def delete_frequent_site(self, site_id: int) -> bool:
        with get_conn(self._db_path) as conn:
            with conn:
                return conn.execute("DELETE FROM frequent_sites WHERE id=?", (site_id,)).rowcount > 0
