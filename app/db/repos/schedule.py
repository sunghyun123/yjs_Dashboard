# app/db/repos/schedule.py
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.db.connection import get_conn

logger = logging.getLogger(__name__)


def _normalize_shift_type(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in ("주간", "day", "DAY"):
        return "주간"
    if raw in ("야간", "night", "NIGHT", "심야", "midnight", "MIDNIGHT"):
        return "야간"
    return ""


def extract_shift_type(data: Dict[str, Any]) -> str:
    """data dict에서 shift_type을 추출·정규화한다. 공개 함수."""
    direct = _normalize_shift_type(data.get("shift_type"))
    if direct:
        return direct
    tags_raw = data.get("tags")
    if isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    elif isinstance(tags_raw, str):
        tags = [s.strip() for s in tags_raw.split(",") if s.strip()]
    else:
        tags = []
    for t in tags:
        normalized = _normalize_shift_type(t)
        if normalized:
            return normalized
    task_text = str(data.get("task") or "")
    if "(주간)" in task_text:
        return "주간"
    if "(야간)" in task_text or "(심야)" in task_text:
        return "야간"
    return ""


def _should_skip_merge(category: str, location: str) -> bool:
    cat = (category or "").strip()
    loc = (location or "").strip()
    if not loc:
        return True
    if cat == "일반 작업":
        return True
    if "(작업)" in cat:
        return True
    if cat in ("점검", "자재입고", "현장답사", "일정"):
        return True
    return False


def _normalize_tags(data: Dict[str, Any]) -> str:
    tags = data.get("tags")
    if isinstance(tags, list):
        return ",".join(str(t) for t in tags)
    if tags is None:
        return ""
    return str(tags)


def _normalize_schedule_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """upsert/insert 양쪽에서 공통으로 사용하는 정규화."""
    d = data.copy()
    d["person"] = str(d.get("person", "") or "").strip()
    d["details"] = d.get("details", "")
    d["category"] = d.get("category", "공사 일정")
    d["date"] = str(d.get("date", "") or "").strip()
    d["location"] = ""
    d["task"] = str(d.get("task", "") or "").strip()
    d["work_code"] = str(d.get("work_code", "") or "").strip()
    d["shift_type"] = extract_shift_type(d)
    d["tags"] = _normalize_tags(d)

    sk = str(d.get("source_kind") or "manual").strip() or "manual"
    d["source_kind"] = sk if sk in ("manual", "photo_plan") else "manual"

    erp_raw = d.get("erp_data")
    if isinstance(erp_raw, dict):
        d["erp_data"] = json.dumps(erp_raw, ensure_ascii=False)
    elif erp_raw is None or erp_raw == "":
        d["erp_data"] = None
    else:
        d["erp_data"] = str(erp_raw)

    raw_puid = d.get("source_photo_upload_id")
    if raw_puid is not None and str(raw_puid).strip():
        try:
            d["source_photo_upload_id"] = int(raw_puid)
        except (TypeError, ValueError):
            d["source_photo_upload_id"] = None
    else:
        d["source_photo_upload_id"] = None

    try:
        d["photo_plan_acknowledged"] = 1 if int(d.get("photo_plan_acknowledged", 0)) else 0
    except (TypeError, ValueError):
        d["photo_plan_acknowledged"] = 0

    return d


class ScheduleRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def upsert(self, data: Dict[str, Any], actor_user: str = "", actor_device: str = "") -> Dict[str, Any]:
        """date+location 병합 규칙으로 INSERT 또는 UPDATE. 반환: {"action": "insert"|"update", "id": int}."""
        d = _normalize_schedule_data(data)
        if not d["date"]:
            raise ValueError("'date' 값이 누락되었습니다.")
        if not d["task"]:
            raise ValueError("'task' 값이 누락되었습니다.")

        now_iso = datetime.utcnow().isoformat()
        skip_merge = _should_skip_merge(d["category"], d["location"])

        with get_conn(self._db_path) as conn:
            existing = None
            if not skip_merge:
                row = conn.execute(
                    "SELECT id FROM field_schedules WHERE date = ? AND location = ? AND deleted_at IS NULL",
                    (d["date"], d["location"]),
                ).fetchone()
                existing = row

            if existing:
                conn.execute(
                    """
                    UPDATE field_schedules
                    SET task=:task, person=:person, details=:details, tags=:tags,
                        work_code=:work_code, shift_type=:shift_type, category=:category,
                        source_kind=:source_kind, source_photo_upload_id=:source_photo_upload_id,
                        photo_plan_acknowledged=:photo_plan_acknowledged, erp_data=:erp_data,
                        created_at=CURRENT_TIMESTAMP,
                        last_actor_user=:last_actor_user, last_actor_device=:last_actor_device,
                        last_actor_at=:last_actor_at
                    WHERE id=:id
                    """,
                    {**d, "id": existing["id"], "last_actor_user": actor_user,
                     "last_actor_device": actor_device, "last_actor_at": now_iso},
                )
                conn.commit()
                return {"action": "update", "id": existing["id"]}
            else:
                max_row = conn.execute(
                    "SELECT COALESCE(MAX(display_order), -1) FROM field_schedules WHERE date=? AND deleted_at IS NULL",
                    (d["date"],),
                ).fetchone()
                next_order = int(max_row[0]) + 1 if max_row else 0
                cursor = conn.execute(
                    """
                    INSERT INTO field_schedules (
                        date, location, task, person, details, tags, work_code, shift_type, category,
                        source_kind, source_photo_upload_id, photo_plan_acknowledged, erp_data,
                        last_actor_user, last_actor_device, last_actor_at, display_order
                    ) VALUES (
                        :date, :location, :task, :person, :details, :tags, :work_code, :shift_type, :category,
                        :source_kind, :source_photo_upload_id, :photo_plan_acknowledged, :erp_data,
                        :last_actor_user, :last_actor_device, :last_actor_at, :display_order
                    )
                    """,
                    {**d, "last_actor_user": actor_user, "last_actor_device": actor_device,
                     "last_actor_at": now_iso, "display_order": next_order},
                )
                conn.commit()
                return {"action": "insert", "id": int(cursor.lastrowid)}

    def insert_row(self, data: Dict[str, Any], actor_user: str = "", actor_device: str = "") -> int:
        """병합 없이 항상 신규 INSERT. 반환: 새 행의 id."""
        d = _normalize_schedule_data(data)
        if not d["date"]:
            raise ValueError("'date' 값이 누락되었습니다.")
        if not d["task"]:
            raise ValueError("'task' 값이 누락되었습니다.")

        now_iso = datetime.utcnow().isoformat()
        with get_conn(self._db_path) as conn:
            with conn:
                max_row = conn.execute(
                    "SELECT COALESCE(MAX(display_order), -1) FROM field_schedules WHERE date=? AND deleted_at IS NULL",
                    (d["date"],),
                ).fetchone()
                next_order = int(max_row[0]) + 1 if max_row else 0
                cursor = conn.execute(
                    """
                    INSERT INTO field_schedules (
                        date, location, task, person, details, tags, work_code, shift_type, category,
                        source_kind, source_photo_upload_id, photo_plan_acknowledged, erp_data,
                        last_actor_user, last_actor_device, last_actor_at, display_order
                    ) VALUES (
                        :date, :location, :task, :person, :details, :tags, :work_code, :shift_type, :category,
                        :source_kind, :source_photo_upload_id, :photo_plan_acknowledged, :erp_data,
                        :last_actor_user, :last_actor_device, :last_actor_at, :display_order
                    )
                    """,
                    {**d, "last_actor_user": actor_user, "last_actor_device": actor_device,
                     "last_actor_at": now_iso, "display_order": next_order},
                )
                return int(cursor.lastrowid)

    def get_by_id(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                       created_at, deleted_at, deleted_by, delete_reason,
                       last_actor_user, last_actor_device, last_actor_at, display_order,
                       source_kind, source_photo_upload_id, photo_plan_acknowledged, erp_data
                FROM field_schedules WHERE id=?
                """,
                (schedule_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_by_id(self, schedule_id: int, data: Dict[str, Any], actor_user: str = "", actor_device: str = "") -> bool:
        now_iso = datetime.utcnow().isoformat()
        with get_conn(self._db_path) as conn:
            with conn:
                prev = conn.execute(
                    "SELECT source_kind, source_photo_upload_id, photo_plan_acknowledged FROM field_schedules WHERE id=? AND deleted_at IS NULL",
                    (schedule_id,),
                ).fetchone()
                if not prev:
                    return False

                sk = str(data.get("source_kind") or prev["source_kind"] or "manual").strip() or "manual"
                sk = sk if sk in ("manual", "photo_plan") else "manual"

                if "source_photo_upload_id" in data:
                    raw = data["source_photo_upload_id"]
                    try:
                        puid = int(raw) if raw is not None and str(raw).strip() else None
                    except (TypeError, ValueError):
                        puid = None
                else:
                    puid = prev["source_photo_upload_id"]

                if "photo_plan_acknowledged" in data:
                    try:
                        ack = 1 if int(data.get("photo_plan_acknowledged", 0)) else 0
                    except (TypeError, ValueError):
                        ack = int(prev["photo_plan_acknowledged"] or 0)
                else:
                    ack = int(prev["photo_plan_acknowledged"] or 0)

                tags = data.get("tags", "")
                if isinstance(tags, list):
                    tags = ",".join(tags)

                erp_raw = data.get("erp_data")
                if isinstance(erp_raw, dict):
                    erp_json = json.dumps(erp_raw, ensure_ascii=False)
                elif erp_raw is None or erp_raw == "":
                    erp_json = None
                else:
                    erp_json = str(erp_raw)

                cursor = conn.execute(
                    """
                    UPDATE field_schedules
                    SET date=:date, location=:location, task=:task, person=:person,
                        details=:details, tags=:tags, work_code=:work_code, shift_type=:shift_type,
                        category=:category, source_kind=:source_kind,
                        source_photo_upload_id=:source_photo_upload_id,
                        photo_plan_acknowledged=:photo_plan_acknowledged, erp_data=:erp_data,
                        created_at=CURRENT_TIMESTAMP,
                        last_actor_user=:last_actor_user, last_actor_device=:last_actor_device,
                        last_actor_at=:last_actor_at
                    WHERE id=:id AND deleted_at IS NULL
                    """,
                    {
                        "id": schedule_id,
                        "date": data.get("date"),
                        "location": "",
                        "task": data.get("task"),
                        "person": str(data.get("person", "") or "").strip(),
                        "details": data.get("details", ""),
                        "tags": tags,
                        "work_code": str(data.get("work_code", "") or "").strip(),
                        "shift_type": extract_shift_type(data),
                        "category": data.get("category", "일반메모"),
                        "source_kind": sk,
                        "source_photo_upload_id": puid,
                        "photo_plan_acknowledged": ack,
                        "erp_data": erp_json,
                        "last_actor_user": actor_user,
                        "last_actor_device": actor_device,
                        "last_actor_at": now_iso,
                    },
                )
                return cursor.rowcount > 0

    def soft_delete(self, schedule_id: int, deleted_by: str, delete_reason: str = "", actor_device: str = "") -> bool:
        now_iso = datetime.utcnow().isoformat()
        with get_conn(self._db_path) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE field_schedules
                    SET deleted_at=?, deleted_by=?, delete_reason=?,
                        last_actor_user=?, last_actor_device=?, last_actor_at=?
                    WHERE id=? AND deleted_at IS NULL
                    """,
                    (now_iso, deleted_by, delete_reason, deleted_by, actor_device, now_iso, schedule_id),
                )
                return cursor.rowcount > 0

    def acknowledge_photo_plan(self, schedule_id: int, actor_user: str = "", actor_device: str = "") -> bool:
        now_iso = datetime.utcnow().isoformat()
        with get_conn(self._db_path) as conn:
            with conn:
                cur = conn.execute(
                    """
                    UPDATE field_schedules
                    SET photo_plan_acknowledged=1, last_actor_user=?, last_actor_device=?, last_actor_at=?
                    WHERE id=? AND deleted_at IS NULL AND source_kind='photo_plan'
                    """,
                    (actor_user, actor_device, now_iso, schedule_id),
                )
                return bool(cur.rowcount)

    def apply_reorder(self, items: List[Dict[str, Any]], actor_user: str = "", actor_device: str = "") -> int:
        if not items:
            return 0
        now_iso = datetime.utcnow().isoformat()
        applied = 0
        with get_conn(self._db_path) as conn:
            with conn:
                for item in items:
                    schedule_id = int(item.get("schedule_id", 0))
                    target_date = str(item.get("date", "")).strip()
                    display_order = int(item.get("display_order", 0))
                    if not schedule_id or not target_date:
                        continue
                    cursor = conn.execute(
                        """
                        UPDATE field_schedules
                        SET date=?, display_order=?, last_actor_user=?, last_actor_device=?, last_actor_at=?
                        WHERE id=? AND deleted_at IS NULL
                        """,
                        (target_date, display_order, actor_user, actor_device, now_iso, schedule_id),
                    )
                    applied += int(cursor.rowcount or 0)
        return applied

    def search_by_keyword(self, date: Optional[str] = None, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM field_schedules WHERE deleted_at IS NULL"
        params: List[Any] = []
        if date:
            query += " AND date=?"
            params.append(date)
        if keyword:
            query += " AND (location LIKE ? OR task LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        query += " ORDER BY date DESC, display_order ASC, created_at DESC"
        try:
            with get_conn(self._db_path) as conn:
                return [dict(row) for row in conn.execute(query, params).fetchall()]
        except Exception as e:
            logger.error("일정 검색 오류: %s", e)
            return []

    def list_window(self, base_date: Optional[str] = None, past_days: int = 3, future_days: int = 7) -> List[Dict[str, Any]]:
        today = datetime.strptime(base_date, "%Y-%m-%d").date() if base_date else datetime.now().date()
        start = (today - timedelta(days=past_days)).strftime("%Y-%m-%d")
        end = (today + timedelta(days=future_days)).strftime("%Y-%m-%d")
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                       source_kind, source_photo_upload_id, photo_plan_acknowledged,
                       datetime(created_at, 'localtime') as created_at
                FROM field_schedules
                WHERE deleted_at IS NULL AND date >= ? AND date <= ?
                ORDER BY date ASC, display_order ASC, created_at ASC
                """,
                (start, end),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                       source_kind, source_photo_upload_id, photo_plan_acknowledged, erp_data,
                       datetime(created_at, 'localtime') as created_at
                FROM field_schedules
                WHERE deleted_at IS NULL AND date >= ? AND date <= ?
                ORDER BY date ASC, display_order ASC, created_at ASC
                """,
                (start_date, end_date),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_by_date(self, target_date: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                       source_kind, source_photo_upload_id, photo_plan_acknowledged, erp_data,
                       deleted_at, deleted_by, delete_reason,
                       last_actor_user, last_actor_device, last_actor_at,
                       datetime(created_at, 'localtime') AS created_at
                FROM field_schedules WHERE date=? ORDER BY created_at DESC
                """,
                (target_date,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_all_for_backup(self) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                       source_kind, source_photo_upload_id, photo_plan_acknowledged, erp_data,
                       deleted_at, deleted_by, delete_reason,
                       last_actor_user, last_actor_device, last_actor_at,
                       datetime(created_at, 'localtime') AS created_at
                FROM field_schedules ORDER BY date ASC, created_at ASC, id ASC
                """,
            ).fetchall()
            return [dict(row) for row in rows]
