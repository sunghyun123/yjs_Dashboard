# app/db/db_manager.py
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import closing
from typing import List, Dict, Any, Optional
import hashlib

# 로거 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DBManager:
    def __init__(self, db_path: str = "schedule.db"):
        """
        초기화 시점에 데이터베이스 경로를 설정하고 테이블 생성 로직을 실행합니다.
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """DB 테이블에 details와 tags 컬럼이 없으면 추가하거나 생성합니다."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                # 1. 기본 테이블 생성 (details, tags 컬럼 추가)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS field_schedules
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 date TEXT,
                                 location TEXT,
                                 task TEXT,
                                 person TEXT,
                                 details TEXT,
                                 tags TEXT,
                                 category TEXT,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)

                # 2. [Migration] 기존 DB를 쓰는 경우를 대비해 컬럼이 없으면 추가
                cursor = conn.execute("PRAGMA table_info(field_schedules)")
                columns = [row[1] for row in cursor.fetchall()]
                if "details" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN details TEXT")
                if "tags" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN tags TEXT")
                if "deleted_at" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN deleted_at TEXT")
                if "deleted_by" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN deleted_by TEXT")
                if "delete_reason" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN delete_reason TEXT")
                if "last_actor_user" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN last_actor_user TEXT")
                if "last_actor_device" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN last_actor_device TEXT")
                if "last_actor_at" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN last_actor_at TEXT")
                if "display_order" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN display_order INTEGER DEFAULT 0")

                # 인증/세션/관리요청/사진업로드 테이블
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS users
                             (
                                 user_id TEXT PRIMARY KEY,
                                 password_hash TEXT NOT NULL,
                                 register_code TEXT NOT NULL,
                                 role TEXT NOT NULL DEFAULT 'worker',
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS sessions
                             (
                                 session_id TEXT PRIMARY KEY,
                                 user_id TEXT NOT NULL,
                                 role TEXT NOT NULL,
                                 device_name TEXT,
                                 expires_at TEXT NOT NULL,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS admin_requests
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 request_type TEXT NOT NULL,
                                 source_category TEXT NOT NULL,
                                 request_text TEXT NOT NULL,
                                 summary TEXT,
                                 payload_json TEXT,
                                 requested_by TEXT,
                                 status TEXT NOT NULL DEFAULT 'pending',
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS photo_uploads
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 category TEXT NOT NULL,
                                 file_path TEXT NOT NULL,
                                 uploaded_by TEXT,
                                 uploaded_device TEXT,
                                 related_date TEXT,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS memo_items
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 memo_type TEXT NOT NULL DEFAULT '일반',
                                 content TEXT NOT NULL,
                                 target_date TEXT NOT NULL,
                                 linked_schedule_id INTEGER,
                                 visibility TEXT NOT NULL DEFAULT 'all',
                                 status TEXT NOT NULL DEFAULT 'active',
                                 last_actor_user TEXT,
                                 last_actor_device TEXT,
                                 last_actor_at TEXT,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS worker_status
                             (
                                 user_name TEXT PRIMARY KEY,
                                 status TEXT NOT NULL DEFAULT '사무실',
                                 location TEXT,
                                 until_time TEXT,
                                 note TEXT,
                                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                 last_actor_user TEXT,
                                 last_actor_device TEXT,
                                 last_actor_at TEXT
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS export_jobs
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 target_date TEXT NOT NULL,
                                 status TEXT NOT NULL DEFAULT 'pending',
                                 output_path TEXT,
                                 message TEXT,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS audit_events
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 entity_type TEXT NOT NULL,
                                 entity_id INTEGER,
                                 action TEXT NOT NULL,
                                 before_json TEXT,
                                 after_json TEXT,
                                 reason TEXT,
                                 actor_user TEXT,
                                 actor_device TEXT,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)

                # 초기 운영용 기본 계정 (최초 1회)
                user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                if user_count == 0:
                    default_pw_hash = hashlib.sha256("admin1234".encode("utf-8")).hexdigest()
                    conn.execute(
                        "INSERT INTO users (user_id, password_hash, register_code, role) VALUES (?, ?, ?, ?)",
                        ("admin", default_pw_hash, "YJS-REGISTER-001", "admin")
                    )

    def upsert_schedule(self, data: Dict[str, Any], actor_user: str = "", actor_device: str = "") -> str:
        """
        똑같은 날짜+장소 데이터가 있으면 수정(UPDATE), 없으면 새로 저장(INSERT) (Upsert)
        생성(create) 및 수정(update) 명령에서 공통으로 사용됩니다.
        """
        db_data = data.copy()
        db_data['person'] = data.get('person', '-')
        db_data['details'] = data.get('details', '')
        db_data['category'] = data.get('category', '공사일정')
        # tags가 리스트 형태면 쉼표로 연결된 문자열로 변환
        if isinstance(db_data.get('tags'), list):
            db_data['tags'] = ",".join(db_data.get('tags', []))
        elif db_data.get('tags') is None:
            db_data['tags'] = ""
        elif not isinstance(db_data.get('tags'), str):
            db_data['tags'] = str(db_data.get('tags'))

        # 필수 키 누락 방어: 프론트/AI 응답에서 일부 필드가 빠져도 DB 바인딩 실패를 막는다.
        for required_key in ['date', 'location', 'task']:
            if required_key not in db_data or db_data[required_key] in [None, ""]:
                raise ValueError(f"'{required_key}' 값이 누락되었습니다.")

        with closing(sqlite3.connect(self.db_path)) as conn:
            # 1. 같은 날짜와 장소가 이미 있는지 확인
            check_sql = "SELECT id FROM field_schedules WHERE date = ? AND location = ? AND deleted_at IS NULL"
            existing = conn.execute(check_sql, (db_data['date'], db_data['location'])).fetchone()

            if existing:
                # 2. 존재하면 UPDATE (수정)
                update_sql = """
                             UPDATE field_schedules
                             SET task       = :task,
                                 person     = :person,
                                 details    = :details,
                                 tags       = :tags,
                                 category   = :category,
                                 created_at = CURRENT_TIMESTAMP,
                                 last_actor_user = :last_actor_user,
                                 last_actor_device = :last_actor_device,
                                 last_actor_at = :last_actor_at
                             WHERE id = ?
                             """
                conn.execute(update_sql, {
                    **db_data,
                    "id": existing[0],
                    "last_actor_user": actor_user,
                    "last_actor_device": actor_device,
                    "last_actor_at": datetime.utcnow().isoformat(),
                })
                conn.commit()
                return f"📍 {db_data['location']} ({db_data['date']}) 일정이 수정되었습니다. (ID: {existing[0]})"
            else:
                # 3. 존재하지 않으면 INSERT (신규)
                insert_sql = """
                             INSERT INTO field_schedules (
                                date, location, task, person, details, tags, category,
                                last_actor_user, last_actor_device, last_actor_at, display_order
                             )
                             VALUES (
                                :date, :location, :task, :person, :details, :tags, :category,
                                :last_actor_user, :last_actor_device, :last_actor_at, :display_order
                             )
                             """
                max_order_row = conn.execute(
                    "SELECT COALESCE(MAX(display_order), -1) FROM field_schedules WHERE date = ? AND deleted_at IS NULL",
                    (db_data["date"],)
                ).fetchone()
                next_order = int(max_order_row[0]) + 1 if max_order_row else 0
                cursor = conn.execute(insert_sql, {
                    **db_data,
                    "last_actor_user": actor_user,
                    "last_actor_device": actor_device,
                    "last_actor_at": datetime.utcnow().isoformat(),
                    "display_order": next_order,
                })
                conn.commit()
                return f"➕ {db_data['location']} ({db_data['date']}) 신규 일정이 등록되었습니다. (ID: {cursor.lastrowid})"

    def search_schedules_by_keyword(self, date: Optional[str] = None, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        [V2 신규] 대화형 UI에서 모호한 명령이 들어왔을 때, 날짜와 키워드(location 또는 task)로 후보 일정을 검색합니다.
        AI가 찾은 후보 리스트를 반환하여 사용자에게 선택지를 제공할 때 사용합니다.
        """
        query = "SELECT * FROM field_schedules WHERE 1=1 AND deleted_at IS NULL"
        params = []

        if date:
            query += " AND date = ?"
            params.append(date)

        if keyword:
            # location이나 task에 키워드가 포함되어 있는지 검색
            query += " AND (location LIKE ? OR task LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        query += " ORDER BY date DESC, display_order ASC, created_at DESC"

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"[DB 에러] 일정 검색 중 오류 발생: {e}")
            return []

    def delete_schedule_by_id(self, schedule_id: int) -> bool:
        """
        [V2 신규] ID를 기반으로 정확하게 일정을 삭제합니다.
        사용자가 AI가 제시한 후보 중 특정 항목의 삭제 버튼을 클릭했을 때 호출됩니다.
        """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    cursor = conn.execute("DELETE FROM field_schedules WHERE id = ?", (schedule_id,))
                    if cursor.rowcount > 0:
                        logger.info(f"일정 삭제 완료: ID {schedule_id}")
                        return True
                    else:
                        logger.warning(f"삭제할 일정을 찾을 수 없음: ID {schedule_id}")
                        return False
        except sqlite3.Error as e:
            logger.error(f"[DB 에러] 일정 삭제 중 오류 발생: {e}")
            return False

    def delete_schedule_by_data(self, date: str, location: str) -> Optional[int]:
        """
        (V1 레거시) 날짜와 장소를 기준으로 일정을 찾아 삭제합니다.
        V2 구조에서는 AI의 오작동 방지를 위해 가급적 delete_schedule_by_id 사용을 권장합니다.
        """
        if not date or not location:
            return None

        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                select_sql = "SELECT id FROM field_schedules WHERE date = ? AND location = ?"
                existing = conn.execute(select_sql, (date, location)).fetchone()

                if existing:
                    target_id = existing[0]
                    delete_sql = "DELETE FROM field_schedules WHERE id = ?"
                    conn.execute(delete_sql, (target_id,))
                    logger.info(f"일정 삭제 완료: ID {target_id} ({date}, {location})")
                    return target_id
                else:
                    return None

    def get_all_schedules_desc(self, target_date: str = None) -> List[Dict[str, Any]]:
        """
        모든 일정 데이터를 최근 날짜 및 등록 순으로 50개까지 가져옵니다. (날짜 필터 없음)
        'dashboard.html'에서 화면을 그릴 때 사용합니다.
        """
        select_query = """
            SELECT id, date, location, task, person, details, tags, category,
                   datetime(created_at, 'localtime') as created_at
            FROM field_schedules
            WHERE deleted_at IS NULL
            ORDER BY date DESC, display_order ASC, created_at DESC
            LIMIT 50
        """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(select_query)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"[DB 에러] {e}")
            return []

    def get_schedules_for_window(self, base_date: Optional[str] = None, past_days: int = 3, future_days: int = 7) -> List[Dict[str, Any]]:
        if base_date:
            today = datetime.strptime(base_date, "%Y-%m-%d").date()
        else:
            today = datetime.now().date()
        start_date = (today - timedelta(days=past_days)).strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=future_days)).strftime("%Y-%m-%d")
        query = """
            SELECT id, date, location, task, person, details, tags, category,
                   datetime(created_at, 'localtime') as created_at
            FROM field_schedules
            WHERE deleted_at IS NULL
              AND date >= ?
              AND date <= ?
            ORDER BY date ASC, display_order ASC, created_at ASC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            return [dict(row) for row in rows]

    def get_schedule_by_id(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, date, location, task, person, details, tags, category, created_at,
                   deleted_at, deleted_by, delete_reason,
                   last_actor_user, last_actor_device, last_actor_at, display_order
            FROM field_schedules
            WHERE id = ?
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, (schedule_id,)).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT user_id, password_hash, register_code, role FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def create_session(self, session_id: str, user_id: str, device_name: str, expires_at: str) -> None:
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("사용자를 찾을 수 없습니다.")
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO sessions (session_id, user_id, role, device_name, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, user_id, user["role"], device_name, expires_at),
                )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT session_id, user_id, role, device_name, expires_at
                FROM sessions
                WHERE session_id = ? AND datetime(expires_at) > datetime('now')
                """,
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, session_id: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def create_admin_request(
        self,
        request_type: str,
        source_category: str,
        request_text: str,
        summary: str,
        payload_json: str = "",
        requested_by: str = "",
    ) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO admin_requests
                    (request_type, source_category, request_text, summary, payload_json, requested_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (request_type, source_category, request_text, summary, payload_json, requested_by),
                )
                return int(cursor.lastrowid)

    def list_admin_requests(
        self,
        status: str = "pending",
        requested_by: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT id, request_type, source_category, request_text, summary, payload_json,
                   requested_by, status, datetime(created_at, 'localtime') AS created_at
            FROM admin_requests
            WHERE status = ?
        """
        params: List[Any] = [status]
        if requested_by and requested_by.strip():
            query += " AND requested_by LIKE ?"
            params.append(f"%{requested_by.strip()}%")
        if since and since.strip():
            query += " AND date(datetime(created_at, 'localtime')) >= date(?)"
            params.append(since.strip()[:10])
        if until and until.strip():
            query += " AND date(datetime(created_at, 'localtime')) <= date(?)"
            params.append(until.strip()[:10])
        query += " ORDER BY id DESC LIMIT 200"
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def get_admin_request_by_id(self, request_id: int) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM admin_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_admin_request_status(self, request_id: int, status: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE admin_requests SET status = ? WHERE id = ?",
                    (status, request_id),
                )

    def update_schedule_by_id(self, schedule_id: int, data: Dict[str, Any], actor_user: str = "", actor_device: str = "") -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE field_schedules
                    SET date = :date,
                        location = :location,
                        task = :task,
                        person = :person,
                        details = :details,
                        tags = :tags,
                        category = :category,
                        created_at = CURRENT_TIMESTAMP,
                        last_actor_user = :last_actor_user,
                        last_actor_device = :last_actor_device,
                        last_actor_at = :last_actor_at
                    WHERE id = :id AND deleted_at IS NULL
                    """,
                    {
                        "id": schedule_id,
                        "date": data.get("date"),
                        "location": data.get("location"),
                        "task": data.get("task"),
                        "person": data.get("person", "-"),
                        "details": data.get("details", ""),
                        "tags": ",".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else data.get("tags", ""),
                        "category": data.get("category", "일반메모"),
                        "last_actor_user": actor_user,
                        "last_actor_device": actor_device,
                        "last_actor_at": datetime.utcnow().isoformat(),
                    },
                )
                return cursor.rowcount > 0

    def apply_schedule_reorder(
        self,
        items: List[Dict[str, Any]],
        actor_user: str = "",
        actor_device: str = "",
    ) -> int:
        """
        클라이언트 드래그 결과를 일괄 반영한다.
        item: {"schedule_id": int, "date": "YYYY-MM-DD", "display_order": int}
        """
        if not items:
            return 0
        now_iso = datetime.utcnow().isoformat()
        applied = 0
        with closing(sqlite3.connect(self.db_path)) as conn:
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
                        SET date = ?,
                            display_order = ?,
                            last_actor_user = ?,
                            last_actor_device = ?,
                            last_actor_at = ?
                        WHERE id = ? AND deleted_at IS NULL
                        """,
                        (target_date, display_order, actor_user, actor_device, now_iso, schedule_id),
                    )
                    applied += int(cursor.rowcount or 0)
        return applied

    def create_audit_event(
        self,
        entity_type: str,
        entity_id: Optional[int],
        action: str,
        before_json: str = "",
        after_json: str = "",
        reason: str = "",
        actor_user: str = "",
        actor_device: str = "",
    ) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO audit_events
                    (entity_type, entity_id, action, before_json, after_json, reason, actor_user, actor_device)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (entity_type, entity_id, action, before_json, after_json, reason, actor_user, actor_device),
                )
                return int(cursor.lastrowid)

    def list_audit_events(
        self,
        limit: int = 200,
        actions: Optional[List[str]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        query = """
            SELECT id, entity_type, entity_id, action, before_json, after_json, reason,
                   actor_user, actor_device,
                   datetime(created_at, 'localtime') AS created_at
            FROM audit_events
        """
        where_parts: List[str] = []
        params: List[Any] = []
        if actions:
            placeholders = ",".join(["?"] * len(actions))
            where_parts.append(f"action IN ({placeholders})")
            params.extend(actions)
        if since and since.strip():
            where_parts.append("date(datetime(created_at, 'localtime')) >= date(?)")
            params.append(since.strip()[:10])
        if until and until.strip():
            where_parts.append("date(datetime(created_at, 'localtime')) <= date(?)")
            params.append(until.strip()[:10])
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(safe_limit)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def soft_delete_schedule_by_id(self, schedule_id: int, deleted_by: str, delete_reason: str = "", actor_device: str = "") -> bool:
        deleted_at = datetime.utcnow().isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE field_schedules
                    SET deleted_at = ?, deleted_by = ?, delete_reason = ?,
                        last_actor_user = ?, last_actor_device = ?, last_actor_at = ?
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    (deleted_at, deleted_by, delete_reason, deleted_by, actor_device, datetime.utcnow().isoformat(), schedule_id),
                )
                return cursor.rowcount > 0

    def save_photo_upload(
        self,
        category: str,
        file_path: str,
        uploaded_by: str,
        uploaded_device: str,
        related_date: str,
    ) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO photo_uploads (category, file_path, uploaded_by, uploaded_device, related_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (category, file_path, uploaded_by, uploaded_device, related_date),
                )
                return int(cursor.lastrowid)

    def create_memo(
        self,
        content: str,
        target_date: str,
        memo_type: str = "일반",
        linked_schedule_id: Optional[int] = None,
        visibility: str = "all",
        actor_user: str = "",
        actor_device: str = "",
    ) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO memo_items (
                        memo_type, content, target_date, linked_schedule_id, visibility, status,
                        last_actor_user, last_actor_device, last_actor_at
                    ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
                    """,
                    (
                        memo_type, content, target_date, linked_schedule_id, visibility,
                        actor_user, actor_device, datetime.utcnow().isoformat()
                    ),
                )
                return int(cursor.lastrowid)

    def list_memos(self, target_date: Optional[str] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT id, memo_type, content, target_date, linked_schedule_id, visibility, status,
                   last_actor_user, last_actor_device, last_actor_at,
                   datetime(created_at, 'localtime') AS created_at
            FROM memo_items
            WHERE status = 'active'
        """
        params: List[Any] = []
        if target_date:
            query += " AND target_date = ?"
            params.append(target_date)
        query += " ORDER BY id DESC LIMIT 200"
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def soft_delete_memo(self, memo_id: int, actor_user: str = "", actor_device: str = "") -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE memo_items
                    SET status = 'deleted',
                        last_actor_user = ?,
                        last_actor_device = ?,
                        last_actor_at = ?
                    WHERE id = ? AND status = 'active'
                    """,
                    (actor_user, actor_device, datetime.utcnow().isoformat(), memo_id),
                )
                return cursor.rowcount > 0

    def upsert_worker_status(
        self,
        user_name: str,
        status: str,
        location: str = "",
        until_time: str = "",
        note: str = "",
        actor_user: str = "",
        actor_device: str = "",
    ) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO worker_status
                    (user_name, status, location, until_time, note, updated_at, last_actor_user, last_actor_device, last_actor_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
                    ON CONFLICT(user_name) DO UPDATE SET
                        status = excluded.status,
                        location = excluded.location,
                        until_time = excluded.until_time,
                        note = excluded.note,
                        updated_at = CURRENT_TIMESTAMP,
                        last_actor_user = excluded.last_actor_user,
                        last_actor_device = excluded.last_actor_device,
                        last_actor_at = excluded.last_actor_at
                    """,
                    (
                        user_name, status, location, until_time, note,
                        actor_user, actor_device, datetime.utcnow().isoformat(),
                    ),
                )

    def apply_outing_auto_return(self) -> int:
        now_iso = datetime.utcnow().isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE worker_status
                    SET status = '사무실',
                        location = '',
                        note = '',
                        updated_at = CURRENT_TIMESTAMP,
                        last_actor_user = 'auto-system',
                        last_actor_device = 'auto-system',
                        last_actor_at = ?
                    WHERE status = '외출' AND until_time IS NOT NULL AND until_time != '' AND until_time <= ?
                    """,
                    (now_iso, now_iso),
                )
                return cursor.rowcount

    def list_worker_status(self) -> List[Dict[str, Any]]:
        self.apply_outing_auto_return()
        query = """
            SELECT user_name, status, location, until_time, note,
                   datetime(updated_at, 'localtime') AS updated_at,
                   last_actor_user, last_actor_device, last_actor_at
            FROM worker_status
            ORDER BY updated_at DESC, user_name ASC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def delete_worker_status(self, user_name: str) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    "DELETE FROM worker_status WHERE user_name = ?",
                    (user_name,),
                )
                return cursor.rowcount > 0

    def get_daily_schedules(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, date, location, task, person, details, tags, category,
                   deleted_at, deleted_by, delete_reason,
                   last_actor_user, last_actor_device, last_actor_at,
                   datetime(created_at, 'localtime') AS created_at
            FROM field_schedules
            WHERE date = ?
            ORDER BY created_at DESC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (target_date,)).fetchall()
            return [dict(row) for row in rows]

    def get_daily_memos(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, memo_type, content, target_date, linked_schedule_id, visibility, status,
                   last_actor_user, last_actor_device, last_actor_at,
                   datetime(created_at, 'localtime') AS created_at
            FROM memo_items
            WHERE target_date = ?
            ORDER BY created_at DESC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (target_date,)).fetchall()
            return [dict(row) for row in rows]

    def create_export_job(self, target_date: str, status: str, output_path: str = "", message: str = "") -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO export_jobs (target_date, status, output_path, message)
                    VALUES (?, ?, ?, ?)
                    """,
                    (target_date, status, output_path, message),
                )
                return int(cursor.lastrowid)

    def has_success_export(self, target_date: str) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT 1 FROM export_jobs WHERE target_date = ? AND status = 'success' LIMIT 1",
                (target_date,),
            ).fetchone()
            return bool(row)

    def insert_worklog(self, data: Dict[str, Any]) -> int:
        insert_query = """
                       INSERT INTO work_logs (project_name, project_code, regular_workers, daily_workers)
                       VALUES (:project_name, :project_code, :regular_workers, :daily_workers)
                       """
        # List 형태인 작업자 명단을 쉼표로 연결된 문자열로 변환
        db_data = {
            "project_name": data.get("project_name", ""),
            "project_code": data.get("project_code", ""),
            "regular_workers": ", ".join(data.get("regular_workers", [])),
            "daily_workers": ", ".join(data.get("daily_workers", []))
        }

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    cursor = conn.execute(insert_query, db_data)
                    return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"[DB 에러] 작업일지 Insert 중 오류 발생: {e}")
            raise