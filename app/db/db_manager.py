# app/db/db_manager.py
import sqlite3
import logging
from datetime import datetime
from contextlib import closing
from typing import List, Dict, Any, Optional

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

    def upsert_schedule(self, data: Dict[str, Any]) -> str:
        """
        똑같은 날짜+장소 데이터가 있으면 수정(UPDATE), 없으면 새로 저장(INSERT) (Upsert)
        생성(create) 및 수정(update) 명령에서 공통으로 사용됩니다.
        """
        db_data = data.copy()
        db_data['person'] = data.get('person', '-')
        # tags가 리스트 형태면 쉼표로 연결된 문자열로 변환
        if isinstance(db_data.get('tags'), list):
            db_data['tags'] = ",".join(db_data.get('tags', []))
        elif db_data.get('tags') is None:
            db_data['tags'] = ""

        with closing(sqlite3.connect(self.db_path)) as conn:
            # 1. 같은 날짜와 장소가 이미 있는지 확인
            check_sql = "SELECT id FROM field_schedules WHERE date = ? AND location = ?"
            existing = conn.execute(check_sql, (data['date'], data['location'])).fetchone()

            if existing:
                # 2. 존재하면 UPDATE (수정)
                update_sql = """
                             UPDATE field_schedules
                             SET task       = :task,
                                 person     = :person,
                                 details    = :details,
                                 tags       = :tags,
                                 category   = :category,
                                 created_at = CURRENT_TIMESTAMP
                             WHERE id = ?
                             """
                conn.execute(update_sql, {**db_data, "id": existing[0]})
                conn.commit()
                return f"📍 {data['location']} ({data['date']}) 일정이 수정되었습니다. (ID: {existing[0]})"
            else:
                # 3. 존재하지 않으면 INSERT (신규)
                insert_sql = """
                             INSERT INTO field_schedules (date, location, task, person, details, tags, category)
                             VALUES (:date, :location, :task, :person, :details, :tags, :category)
                             """
                cursor = conn.execute(insert_sql, db_data)
                conn.commit()
                return f"➕ {data['location']} ({data['date']}) 신규 일정이 등록되었습니다. (ID: {cursor.lastrowid})"

    def search_schedules_by_keyword(self, date: Optional[str] = None, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        [V2 신규] 대화형 UI에서 모호한 명령이 들어왔을 때, 날짜와 키워드(location 또는 task)로 후보 일정을 검색합니다.
        AI가 찾은 후보 리스트를 반환하여 사용자에게 선택지를 제공할 때 사용합니다.
        """
        query = "SELECT * FROM field_schedules WHERE 1=1"
        params = []

        if date:
            query += " AND date = ?"
            params.append(date)

        if keyword:
            # location이나 task에 키워드가 포함되어 있는지 검색
            query += " AND (location LIKE ? OR task LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        query += " ORDER BY date DESC, created_at DESC"

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
            ORDER BY date DESC, created_at DESC
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