# app/db/db_manager.py
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import closing
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
import hashlib
import secrets

# 로거 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# DB Manager 클래스
class DBManager:
    def __init__(self, db_path: str = "schedule.db"):
        """
        초기화 시점에 데이터베이스 경로를 설정하고 테이블 생성 로직을 실행합니다.
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """DB 테이블에 일정 확장 컬럼(work_code, shift_type 등)이 없으면 추가하거나 생성합니다."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                # 1. 기본 테이블 생성
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
                                 work_code TEXT,
                                 shift_type TEXT,
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
                if "work_code" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN work_code TEXT")
                if "shift_type" not in columns:
                    conn.execute("ALTER TABLE field_schedules ADD COLUMN shift_type TEXT")
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
                if "source_kind" not in columns:
                    conn.execute(
                        "ALTER TABLE field_schedules ADD COLUMN source_kind TEXT DEFAULT 'manual'"
                    )
                if "source_photo_upload_id" not in columns:
                    conn.execute(
                        "ALTER TABLE field_schedules ADD COLUMN source_photo_upload_id INTEGER"
                    )
                if "photo_plan_acknowledged" not in columns:
                    conn.execute(
                        "ALTER TABLE field_schedules ADD COLUMN photo_plan_acknowledged INTEGER NOT NULL DEFAULT 0"
                    )

                # 인증/세션/관리요청/사진업로드 테이블
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS users
                             (
                                 user_id TEXT PRIMARY KEY,
                                 user_name TEXT,
                                 password_hash TEXT NOT NULL,
                                 password_plain TEXT,
                                 register_code TEXT NOT NULL,
                                 role TEXT NOT NULL DEFAULT 'worker',
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
                if "user_name" not in user_columns:
                    conn.execute("ALTER TABLE users ADD COLUMN user_name TEXT")
                if "password_plain" not in user_columns:
                    conn.execute("ALTER TABLE users ADD COLUMN password_plain TEXT")
                # 보안 강화: 레거시 평문 비밀번호는 더 이상 사용하지 않으므로 초기화
                if "password_plain" in user_columns:
                    conn.execute("UPDATE users SET password_plain = NULL WHERE password_plain IS NOT NULL AND password_plain != ''")
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
                                 file_size INTEGER DEFAULT 0,
                                 file_sha256 TEXT DEFAULT '',
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)
                photo_columns = [row[1] for row in conn.execute("PRAGMA table_info(photo_uploads)").fetchall()]
                if "file_size" not in photo_columns:
                    conn.execute("ALTER TABLE photo_uploads ADD COLUMN file_size INTEGER DEFAULT 0")
                if "file_sha256" not in photo_columns:
                    conn.execute("ALTER TABLE photo_uploads ADD COLUMN file_sha256 TEXT DEFAULT ''")
                # 메모 기능 제거: 기존 테이블이 있어도 정리한다.
                conn.execute("DROP TABLE IF EXISTS memo_items")
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
                             CREATE TABLE IF NOT EXISTS field_staff
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 name TEXT NOT NULL UNIQUE,
                                 sort_order INTEGER DEFAULT 0
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS outing_staff
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 name TEXT NOT NULL UNIQUE,
                                 sort_order INTEGER DEFAULT 0
                             )
                             """)
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS frequent_sites
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 title TEXT NOT NULL,
                                 url TEXT NOT NULL UNIQUE,
                                 sort_order INTEGER DEFAULT 0,
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
                conn.execute("""
                             CREATE TABLE IF NOT EXISTS chat_events
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 user_id TEXT,
                                 input_category TEXT,
                                 intent TEXT,
                                 message_text TEXT,
                                 response_status TEXT NOT NULL DEFAULT 'success',
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                             )
                             """)

    @staticmethod
    def _normalize_shift_type(value: Any) -> str:
        raw = str(value or "").strip()
        if raw in ("주간", "day", "DAY"):
            return "주간"
        if raw in ("야간", "night", "NIGHT", "심야", "midnight", "MIDNIGHT"):
            return "야간"
        return ""

    @classmethod
    def _extract_shift_type(cls, data: Dict[str, Any]) -> str:
        # 1) 신규 표준 필드 우선
        direct = cls._normalize_shift_type(data.get("shift_type"))
        if direct:
            return direct
        # 2) 하위 호환: 기존 tags 배열/문자열
        tags_raw = data.get("tags")
        tags: List[str]
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        elif isinstance(tags_raw, str):
            tags = [s.strip() for s in tags_raw.split(",") if s.strip()]
        else:
            tags = []
        for t in tags:
            normalized = cls._normalize_shift_type(t)
            if normalized:
                return normalized
        # 3) 하위 호환: task 텍스트 내 "(야간)" 등 표기
        task_text = str(data.get("task") or "")
        if "(주간)" in task_text:
            return "주간"
        if "(야간)" in task_text or "(심야)" in task_text:
            return "야간"
        return ""

    @staticmethod
    def _should_skip_date_location_merge(category: str, location: str) -> bool:
        """
        일반 작업/레거시 카테고리는 동일 날짜+지역으로 병합하지 않고 항상 신규 행으로 넣는다.
        지역이 비어 있으면 날짜+지역 병합 키를 쓸 수 없으므로 병합하지 않는다.
        """
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

    def upsert_schedule(self, data: Dict[str, Any], actor_user: str = "", actor_device: str = "") -> str:
        """
        똑같은 날짜+장소 데이터가 있으면 수정(UPDATE), 없으면 새로 저장(INSERT) (Upsert)
        생성(create) 및 수정(update) 명령에서 공통으로 사용됩니다.
        """
        db_data = data.copy()
        db_data['person'] = str(data.get('person', '') or '').strip()
        db_data['details'] = data.get('details', '')
        db_data['category'] = data.get('category', '공사 일정')
        db_data['date'] = str(db_data.get('date', "") or "").strip()
        # 일정 등록 정책 변경: location은 더 이상 일정 필수/입력 필드로 쓰지 않는다.
        db_data['location'] = ""
        db_data['task'] = str(db_data.get('task', "") or "").strip()
        db_data['work_code'] = str(db_data.get('work_code', "") or "").strip()
        db_data['shift_type'] = self._extract_shift_type(db_data)
        # tags가 리스트 형태면 쉼표로 연결된 문자열로 변환
        if isinstance(db_data.get('tags'), list):
            db_data['tags'] = ",".join(db_data.get('tags', []))
        elif db_data.get('tags') is None:
            db_data['tags'] = ""
        elif not isinstance(db_data.get('tags'), str):
            db_data['tags'] = str(db_data.get('tags'))

        sk = str(data.get("source_kind") or "manual").strip() or "manual"
        if sk not in ("manual", "photo_plan"):
            sk = "manual"
        db_data["source_kind"] = sk
        raw_puid = data.get("source_photo_upload_id")
        if raw_puid is not None and str(raw_puid).strip() != "":
            try:
                db_data["source_photo_upload_id"] = int(raw_puid)
            except (TypeError, ValueError):
                db_data["source_photo_upload_id"] = None
        else:
            db_data["source_photo_upload_id"] = None
        try:
            db_data["photo_plan_acknowledged"] = 1 if int(data.get("photo_plan_acknowledged", 0)) else 0
        except (TypeError, ValueError):
            db_data["photo_plan_acknowledged"] = 0

        if not db_data['date']:
            raise ValueError("'date' 값이 누락되었습니다.")
        if not db_data['task']:
            raise ValueError("'task' 값이 누락되었습니다.")

        skip_merge = self._should_skip_date_location_merge(db_data['category'], db_data['location'])
        loc_label = db_data['location'] or "지역 미정"

        with closing(sqlite3.connect(self.db_path)) as conn:
            existing = None
            if not skip_merge:
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
                                 work_code  = :work_code,
                                 shift_type = :shift_type,
                                 category   = :category,
                                 source_kind = :source_kind,
                                 source_photo_upload_id = :source_photo_upload_id,
                                 photo_plan_acknowledged = :photo_plan_acknowledged,
                                 created_at = CURRENT_TIMESTAMP,
                                 last_actor_user = :last_actor_user,
                                 last_actor_device = :last_actor_device,
                                 last_actor_at = :last_actor_at
                             WHERE id = :id
                             """
                conn.execute(update_sql, {
                    **db_data,
                    "id": existing[0],
                    "last_actor_user": actor_user,
                    "last_actor_device": actor_device,
                    "last_actor_at": datetime.utcnow().isoformat(),
                })
                conn.commit()
                return f"📍 {loc_label} ({db_data['date']}) 일정이 수정되었습니다. (ID: {existing[0]})"
            else:
                # 3. 존재하지 않으면 INSERT (신규)
                insert_sql = """
                             INSERT INTO field_schedules (
                                date, location, task, person, details, tags, work_code, shift_type, category,
                                source_kind, source_photo_upload_id, photo_plan_acknowledged,
                                last_actor_user, last_actor_device, last_actor_at, display_order
                             )
                             VALUES (
                                :date, :location, :task, :person, :details, :tags, :work_code, :shift_type, :category,
                                :source_kind, :source_photo_upload_id, :photo_plan_acknowledged,
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
                return f"➕ {loc_label} ({db_data['date']}) 신규 일정이 등록되었습니다. (ID: {cursor.lastrowid})"

    def insert_schedule_row(self, data: Dict[str, Any], actor_user: str = "", actor_device: str = "") -> int:
        """
        날짜+지역 병합 없이 항상 신규 INSERT. 공사일정계획서 사진 반영 등에 사용.
        """
        db_data = data.copy()
        db_data["person"] = str(data.get("person", "") or "").strip()
        db_data["details"] = data.get("details", "")
        db_data["category"] = data.get("category", "공사 일정")
        db_data["date"] = str(db_data.get("date", "") or "").strip()
        db_data["location"] = ""
        db_data["task"] = str(db_data.get("task", "") or "").strip()
        db_data["work_code"] = str(db_data.get("work_code", "") or "").strip()
        db_data["shift_type"] = self._extract_shift_type(db_data)
        if isinstance(db_data.get("tags"), list):
            db_data["tags"] = ",".join(db_data.get("tags", []))
        elif db_data.get("tags") is None:
            db_data["tags"] = ""
        elif not isinstance(db_data.get("tags"), str):
            db_data["tags"] = str(db_data.get("tags"))
        sk = str(data.get("source_kind") or "manual").strip() or "manual"
        if sk not in ("manual", "photo_plan"):
            sk = "manual"
        db_data["source_kind"] = sk
        raw_puid = data.get("source_photo_upload_id")
        if raw_puid is not None and str(raw_puid).strip() != "":
            try:
                db_data["source_photo_upload_id"] = int(raw_puid)
            except (TypeError, ValueError):
                db_data["source_photo_upload_id"] = None
        else:
            db_data["source_photo_upload_id"] = None
        try:
            db_data["photo_plan_acknowledged"] = 1 if int(data.get("photo_plan_acknowledged", 0)) else 0
        except (TypeError, ValueError):
            db_data["photo_plan_acknowledged"] = 0
        if not db_data["date"]:
            raise ValueError("'date' 값이 누락되었습니다.")
        if not db_data["task"]:
            raise ValueError("'task' 값이 누락되었습니다.")
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                max_order_row = conn.execute(
                    "SELECT COALESCE(MAX(display_order), -1) FROM field_schedules WHERE date = ? AND deleted_at IS NULL",
                    (db_data["date"],),
                ).fetchone()
                next_order = int(max_order_row[0]) + 1 if max_order_row else 0
                cursor = conn.execute(
                    """
                    INSERT INTO field_schedules (
                       date, location, task, person, details, tags, work_code, shift_type, category,
                       source_kind, source_photo_upload_id, photo_plan_acknowledged,
                       last_actor_user, last_actor_device, last_actor_at, display_order
                    )
                    VALUES (
                       :date, :location, :task, :person, :details, :tags, :work_code, :shift_type, :category,
                       :source_kind, :source_photo_upload_id, :photo_plan_acknowledged,
                       :last_actor_user, :last_actor_device, :last_actor_at, :display_order
                    )
                    """,
                    {
                        **db_data,
                        "last_actor_user": actor_user,
                        "last_actor_device": actor_device,
                        "last_actor_at": datetime.utcnow().isoformat(),
                        "display_order": next_order,
                    },
                )
                return int(cursor.lastrowid)

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
            SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                   source_kind, source_photo_upload_id, photo_plan_acknowledged,
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
            SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                   source_kind, source_photo_upload_id, photo_plan_acknowledged,
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

    def search_schedules_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                   source_kind, source_photo_upload_id, photo_plan_acknowledged,
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
            SELECT id, date, location, task, person, details, tags, work_code, shift_type, category, created_at,
                   deleted_at, deleted_by, delete_reason,
                   last_actor_user, last_actor_device, last_actor_at, display_order,
                   source_kind, source_photo_upload_id, photo_plan_acknowledged
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
                "SELECT user_id, user_name, password_hash, register_code, role FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_name(self, user_name: str) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT user_id, user_name
                FROM users
                WHERE user_name = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_name,),
            ).fetchone()
            return dict(row) if row else None

    def create_user(
        self,
        user_name: str,
        user_id: str,
        password: str,
        role: str = "worker",
        register_code: str = "",
    ) -> None:
        u_name = (user_name or "").strip()
        u_id = (user_id or "").strip()
        pw = password or ""
        if not u_name:
            raise ValueError("사용자 이름을 입력해 주세요.")
        if not u_id:
            raise ValueError("아이디를 입력해 주세요.")
        if not pw:
            raise ValueError("비밀번호를 입력해 주세요.")
        pw_hash = hashlib.sha256(pw.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO users (user_id, user_name, password_hash, register_code, role)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (u_id, u_name, pw_hash, register_code, role),
                )

    def ensure_oauth_user(self, user_id: str, user_name: str, role: str) -> None:
        """
        카카오 화이트리스트 로그인용: users 행이 없으면 임의 비밀번호 해시로 생성하고,
        있으면 표시 이름·역할을 화이트리스트 기준으로 맞춘다.
        """
        u_id = (user_id or "").strip()
        u_name = (user_name or "").strip() or u_id
        r = (role or "").strip().lower()
        r_db = "admin" if r == "admin" else "worker"
        if not u_id:
            raise ValueError("user_id가 비어 있습니다.")
        random_pw = secrets.token_urlsafe(48)
        pw_hash = hashlib.sha256(random_pw.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (u_id,)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE users SET user_name = ?, role = ?, password_plain = NULL WHERE user_id = ?",
                        (u_name, r_db, u_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO users (user_id, user_name, password_hash, register_code, role)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (u_id, u_name, pw_hash, "", r_db),
                    )

    def reset_user_password(self, user_id: str, user_name: str, new_password: str) -> bool:
        u_id = (user_id or "").strip()
        u_name = (user_name or "").strip()
        pw = new_password or ""
        if not u_id or not u_name or not pw:
            return False
        pw_hash = hashlib.sha256(pw.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, password_plain = NULL
                    WHERE user_id = ? AND user_name = ?
                    """,
                    (pw_hash, u_id, u_name),
                )
                return cursor.rowcount > 0

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
                prev = conn.execute(
                    "SELECT source_kind, source_photo_upload_id, photo_plan_acknowledged FROM field_schedules WHERE id = ? AND deleted_at IS NULL",
                    (schedule_id,),
                ).fetchone()
                prev_sk = (prev[0] if prev else None) or "manual"
                prev_puid = prev[1] if prev and len(prev) > 1 else None
                prev_ack = int(prev[2] or 0) if prev and len(prev) > 2 else 0
                if "source_kind" in data:
                    sk = str(data.get("source_kind") or "manual").strip() or "manual"
                    if sk not in ("manual", "photo_plan"):
                        sk = "manual"
                else:
                    sk = str(prev_sk).strip() or "manual"
                if "source_photo_upload_id" in data:
                    raw_puid = data.get("source_photo_upload_id")
                    if raw_puid is not None and str(raw_puid).strip() != "":
                        try:
                            puid = int(raw_puid)
                        except (TypeError, ValueError):
                            puid = None
                    else:
                        puid = None
                else:
                    puid = prev_puid
                if "photo_plan_acknowledged" in data:
                    try:
                        ack = 1 if int(data.get("photo_plan_acknowledged", 0)) else 0
                    except (TypeError, ValueError):
                        ack = prev_ack
                else:
                    ack = prev_ack
                cursor = conn.execute(
                    """
                    UPDATE field_schedules
                    SET date = :date,
                        location = :location,
                        task = :task,
                        person = :person,
                        details = :details,
                        tags = :tags,
                        work_code = :work_code,
                        shift_type = :shift_type,
                        category = :category,
                        source_kind = :source_kind,
                        source_photo_upload_id = :source_photo_upload_id,
                        photo_plan_acknowledged = :photo_plan_acknowledged,
                        created_at = CURRENT_TIMESTAMP,
                        last_actor_user = :last_actor_user,
                        last_actor_device = :last_actor_device,
                        last_actor_at = :last_actor_at
                    WHERE id = :id AND deleted_at IS NULL
                    """,
                    {
                        "id": schedule_id,
                        "date": data.get("date"),
                        "location": "",
                        "task": data.get("task"),
                        "person": str(data.get("person", "") or "").strip(),
                        "details": data.get("details", ""),
                        "tags": ",".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else data.get("tags", ""),
                        "work_code": str(data.get("work_code", "") or "").strip(),
                        "shift_type": self._extract_shift_type(data),
                        "category": data.get("category", "일반메모"),
                        "source_kind": sk,
                        "source_photo_upload_id": puid,
                        "photo_plan_acknowledged": ack,
                        "last_actor_user": actor_user,
                        "last_actor_device": actor_device,
                        "last_actor_at": datetime.utcnow().isoformat(),
                    },
                )
                return cursor.rowcount > 0

    def acknowledge_photo_plan_schedule(self, schedule_id: int, actor_user: str = "", actor_device: str = "") -> bool:
        """사진 추출 일정(source_kind=photo_plan)에 대해 '검토 완료' 표시. 자동추출 배지 숨김용."""
        now_iso = datetime.utcnow().isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cur = conn.execute(
                    """
                    UPDATE field_schedules
                    SET photo_plan_acknowledged = 1,
                        last_actor_user = ?,
                        last_actor_device = ?,
                        last_actor_at = ?
                    WHERE id = ? AND deleted_at IS NULL AND source_kind = 'photo_plan'
                    """,
                    (actor_user, actor_device, now_iso, schedule_id),
                )
                return bool(cur.rowcount)

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
        file_size: int = 0,
        file_sha256: str = "",
    ) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO photo_uploads (category, file_path, uploaded_by, uploaded_device, related_date, file_size, file_sha256)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (category, file_path, uploaded_by, uploaded_device, related_date, int(file_size or 0), str(file_sha256 or "")),
                )
                return int(cursor.lastrowid)

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

    @staticmethod
    def _parse_local_datetime(value: str) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None
        # datetime-local 입력값(YYYY-MM-DDTHH:MM[:SS])과 기존 ISO 문자열을 모두 허용한다.
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

    def apply_outing_auto_return(self) -> int:
        """
        until_time 이 APP_TIMEZONE 기준 현재 시각 이하인 외출을 사무실로 되돌린다.
        (브라우저가 저장한 날짜+시각은 타임존 정보가 없으므로 APP_TIMEZONE 에 붙여 비교)
        """
        from app.core.config import settings

        tz_name = (getattr(settings, "APP_TIMEZONE", None) or "Asia/Seoul").strip() or "Asia/Seoul"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Seoul")
        now_z = datetime.now(tz)

        expired_users: List[str] = []
        n = 0
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                rows = conn.execute(
                    """
                    SELECT user_name, until_time
                    FROM worker_status
                    WHERE status = '외출' AND until_time IS NOT NULL AND until_time != ''
                    """,
                ).fetchall()
                for row in rows:
                    naive = self._parse_local_datetime(row["until_time"])
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
                expired_snapshot = list(expired_users)
                placeholders = ",".join(["?"] * len(expired_users))
                now_iso = datetime.utcnow().isoformat()
                params: List[Any] = [now_iso, *expired_users]
                cursor = conn.execute(
                    f"""
                    UPDATE worker_status
                    SET status = '사무실',
                        location = '',
                        until_time = '',
                        note = '',
                        updated_at = CURRENT_TIMESTAMP,
                        last_actor_user = 'auto-system',
                        last_actor_device = 'auto-system',
                        last_actor_at = ?
                    WHERE user_name IN ({placeholders})
                    """,
                    tuple(params),
                )
                n = int(cursor.rowcount or 0)
        if n > 0:
            try:
                self.create_audit_event(
                    entity_type="worker_status",
                    entity_id=None,
                    action="outing_auto_return",
                    before_json=json.dumps({"users": expired_snapshot}, ensure_ascii=False),
                    after_json=json.dumps({"status": "사무실", "count": n}, ensure_ascii=False),
                    reason="until_time 경과 자동 사무실 복귀",
                    actor_user="auto-system",
                    actor_device="auto-system",
                )
            except Exception as ex:
                logger.warning("outing_auto_return audit 로그 실패(무시): %s", ex)
        return n

    def list_worker_status(self) -> List[Dict[str, Any]]:
        self.apply_outing_auto_return()
        query = """
            SELECT user_name, status, location, until_time, note,
                   datetime(updated_at, 'localtime') AS updated_at,
                   last_actor_user, last_actor_device, last_actor_at
            FROM worker_status
            ORDER BY CASE status
                        WHEN '외출' THEN 1
                        WHEN '사무실' THEN 2
                        WHEN '야간작업' THEN 3
                        WHEN '휴가' THEN 4
                        ELSE 9
                     END ASC,
                     updated_at DESC,
                     user_name ASC
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

    def list_field_staff(self) -> List[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, name, sort_order FROM field_staff ORDER BY sort_order ASC, name ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    def add_field_staff(self, name: str, sort_order: int = 0) -> int:
        n = (name or "").strip()
        if not n:
            raise ValueError("이름이 필요합니다.")
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO field_staff (name, sort_order) VALUES (?, ?)",
                    (n, sort_order),
                )
                return int(cursor.lastrowid)

    def delete_field_staff(self, staff_id: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM field_staff WHERE id = ?", (staff_id,))
                return cursor.rowcount > 0

    def list_outing_staff(self) -> List[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, name, sort_order FROM outing_staff ORDER BY sort_order ASC, id ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    def add_outing_staff(self, name: str, sort_order: int = 0) -> int:
        n = (name or "").strip()
        if not n:
            raise ValueError("이름이 필요합니다.")
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO outing_staff (name, sort_order) VALUES (?, ?)",
                    (n, sort_order),
                )
                return int(cursor.lastrowid)

    def delete_outing_staff(self, staff_id: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM outing_staff WHERE id = ?", (staff_id,))
                return cursor.rowcount > 0

    def list_frequent_sites(self) -> List[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, url, sort_order FROM frequent_sites ORDER BY sort_order ASC, id ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    def add_frequent_site(self, title: str, url: str, sort_order: int = 0) -> int:
        t = (title or "").strip()
        u = (url or "").strip()
        if not t:
            raise ValueError("사이트 이름이 필요합니다.")
        if not u:
            raise ValueError("사이트 URL이 필요합니다.")
        if not (u.startswith("http://") or u.startswith("https://")):
            raise ValueError("URL은 http:// 또는 https:// 로 시작해야 합니다.")
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO frequent_sites (title, url, sort_order) VALUES (?, ?, ?)",
                    (t, u, sort_order),
                )
                return int(cursor.lastrowid)

    def delete_frequent_site(self, site_id: int) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM frequent_sites WHERE id = ?", (site_id,))
                return cursor.rowcount > 0

    def get_daily_schedules(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                   source_kind, source_photo_upload_id, photo_plan_acknowledged,
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

    def get_all_schedules_for_backup(self) -> List[Dict[str, Any]]:
        query = """
            SELECT id, date, location, task, person, details, tags, work_code, shift_type, category,
                   source_kind, source_photo_upload_id, photo_plan_acknowledged,
                   deleted_at, deleted_by, delete_reason,
                   last_actor_user, last_actor_device, last_actor_at,
                   datetime(created_at, 'localtime') AS created_at
            FROM field_schedules
            ORDER BY date ASC, created_at ASC, id ASC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()
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

    def get_daily_admin_requests(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, request_type, source_category, request_text, summary, payload_json, requested_by, status,
                   datetime(created_at, 'localtime') AS created_at
            FROM admin_requests
            WHERE date(datetime(created_at, 'localtime')) = ?
            ORDER BY created_at DESC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (target_date,)).fetchall()
            return [dict(row) for row in rows]

    def get_daily_photo_uploads(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, category, file_path, uploaded_by, uploaded_device, related_date,
                   datetime(created_at, 'localtime') AS created_at
            FROM photo_uploads
            WHERE related_date = ?
               OR date(datetime(created_at, 'localtime')) = ?
            ORDER BY created_at DESC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (target_date, target_date)).fetchall()
            return [dict(row) for row in rows]

    def get_daily_audit_events(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, entity_type, entity_id, action, reason, actor_user, actor_device,
                   datetime(created_at, 'localtime') AS created_at
            FROM audit_events
            WHERE date(datetime(created_at, 'localtime')) = ?
            ORDER BY created_at DESC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (target_date,)).fetchall()
            return [dict(row) for row in rows]

    def get_daily_login_sessions(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT session_id, user_id, role, device_name, expires_at,
                   datetime(created_at, 'localtime') AS created_at
            FROM sessions
            WHERE date(datetime(created_at, 'localtime')) = ?
            ORDER BY created_at DESC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (target_date,)).fetchall()
            return [dict(row) for row in rows]

    def log_chat_event(
        self,
        user_id: str,
        input_category: str,
        message_text: str,
        intent: str = "",
        response_status: str = "success",
    ) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO chat_events (user_id, input_category, intent, message_text, response_status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (user_id or "").strip(),
                        (input_category or "").strip(),
                        (intent or "").strip(),
                        (message_text or "").strip(),
                        (response_status or "success").strip(),
                    ),
                )
                return int(cursor.lastrowid)

    def get_daily_chat_events(self, target_date: str) -> List[Dict[str, Any]]:
        query = """
            SELECT id, user_id, input_category, intent, message_text, response_status,
                   datetime(created_at, 'localtime') AS created_at
            FROM chat_events
            WHERE date(datetime(created_at, 'localtime')) = ?
            ORDER BY created_at DESC
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (target_date,)).fetchall()
            return [dict(row) for row in rows]

    def get_daily_backup_metrics(self, target_date: str) -> Dict[str, Any]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            active_schedule_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM field_schedules
                WHERE date = ? AND deleted_at IS NULL
                """,
                (target_date,),
            ).fetchone()["cnt"]
            schedule_created_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM field_schedules
                WHERE date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date,),
            ).fetchone()["cnt"]
            outing_status_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM worker_status",
            ).fetchone()["cnt"]
            admin_request_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM admin_requests
                WHERE date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date,),
            ).fetchone()["cnt"]
            photo_upload_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM photo_uploads
                WHERE related_date = ?
                   OR date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date, target_date),
            ).fetchone()["cnt"]
            audit_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM audit_events
                WHERE date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date,),
            ).fetchone()["cnt"]
            login_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM sessions
                WHERE date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date,),
            ).fetchone()["cnt"]
            chat_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM chat_events
                WHERE date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date,),
            ).fetchone()["cnt"]
            update_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM audit_events
                WHERE entity_type = 'schedule'
                  AND action = 'update'
                  AND date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date,),
            ).fetchone()["cnt"]
            delete_count = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM audit_events
                WHERE entity_type = 'schedule'
                  AND action = 'delete'
                  AND date(datetime(created_at, 'localtime')) = ?
                """,
                (target_date,),
            ).fetchone()["cnt"]

            active_users_query = """
                SELECT DISTINCT actor_user AS user_name FROM (
                    SELECT COALESCE(last_actor_user, '') AS actor_user
                    FROM field_schedules
                    WHERE date(last_actor_at) = ?
                    UNION ALL
                    SELECT COALESCE(requested_by, '') AS actor_user
                    FROM admin_requests
                    WHERE date(datetime(created_at, 'localtime')) = ?
                    UNION ALL
                    SELECT COALESCE(uploaded_by, '') AS actor_user
                    FROM photo_uploads
                    WHERE related_date = ?
                       OR date(datetime(created_at, 'localtime')) = ?
                    UNION ALL
                    SELECT COALESCE(actor_user, '') AS actor_user
                    FROM audit_events
                    WHERE date(datetime(created_at, 'localtime')) = ?
                    UNION ALL
                    SELECT COALESCE(user_id, '') AS actor_user
                    FROM sessions
                    WHERE date(datetime(created_at, 'localtime')) = ?
                    UNION ALL
                    SELECT COALESCE(user_id, '') AS actor_user
                    FROM chat_events
                    WHERE date(datetime(created_at, 'localtime')) = ?
                )
                WHERE user_name != ''
            """
            daily_active_users = conn.execute(
                active_users_query,
                (
                    target_date,
                    target_date,
                    target_date,
                    target_date,
                    target_date,
                    target_date,
                    target_date,
                ),
            ).fetchall()
            dau_count = len(daily_active_users)

            return {
                "target_date": target_date,
                "active_schedule_count": int(active_schedule_count or 0),
                "schedule_created_count": int(schedule_created_count or 0),
                "outing_status_snapshot_count": int(outing_status_count or 0),
                "admin_request_count": int(admin_request_count or 0),
                "photo_upload_count": int(photo_upload_count or 0),
                "audit_event_count": int(audit_count or 0),
                "login_session_count": int(login_count or 0),
                "chat_count": int(chat_count or 0),
                "schedule_update_count": int(update_count or 0),
                "schedule_delete_count": int(delete_count or 0),
                "daily_active_user_count": int(dau_count),
            }
