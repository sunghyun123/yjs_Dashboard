import sqlite3
import logging
from datetime import datetime
from contextlib import closing
from typing import List, Dict, Any

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
        """
        [기능 1] DB 파일과 테이블이 없으면 자동 생성합니다.
        """
        create_table_query = """
                             CREATE TABLE IF NOT EXISTS field_schedules \
                             ( \
                                 id \
                                 INTEGER \
                                 PRIMARY \
                                 KEY \
                                 AUTOINCREMENT, \
                                 date \
                                 TEXT, \
                                 location \
                                 TEXT, \
                                 task \
                                 TEXT, \
                                 person \
                                 TEXT, \
                                 category \
                                 TEXT, \
                                 created_at \
                                 TIMESTAMP \
                                 DEFAULT \
                                 CURRENT_TIMESTAMP
                             ) \
                             """
        # closing: 블록을 빠져나갈 때 conn.close()를 확실하게 호출 (누수 방지)
        # with conn: 블록 내에서 에러가 없으면 자동 commit, 에러 시 rollback 처리
        with closing(sqlite3.connect(self.db_path)) as conn:
            with conn:
                conn.execute(create_table_query)
        logger.info(f"데이터베이스 초기화 완료 (경로: {self.db_path})")

    def insert_schedule(self, data: Dict[str, Any]) -> int:
        """
        [기능 2] AI가 파싱한 JSON 데이터(딕셔너리)를 받아 DB에 Insert 합니다.
        성공 시 생성된 레코드의 ID를 반환합니다.
        """
        insert_query = """
                       INSERT INTO field_schedules (date, location, task, person, category)
                       VALUES (:date, :location, :task, :person, :category) \
                       """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                with conn:
                    # 딕셔너리의 키 이름과 쿼리의 :이름 이 매칭되어 안전하게 삽입됨
                    cursor = conn.execute(insert_query, data)
                    inserted_id = cursor.lastrowid

            logger.info(f"일정 등록 완료 (ID: {inserted_id})")
            return inserted_id

        except sqlite3.Error as e:
            logger.error(f"[DB 에러] 일정 Insert 중 오류 발생: {e}")
            raise  # API 단에서 500 에러 처리를 위해 예외를 다시 던짐

    def get_todays_schedules(self, target_date: str = None) -> List[Dict[str, Any]]:
        """
        [기능 3] 상황판에 띄울 오늘자(또는 특정 날짜) 데이터를 Select 해서 반환합니다.
        """
        # 날짜 지정이 없으면 오늘 날짜를 "YYYY-MM-DD" 형태로 생성
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")

        select_query = """
                       SELECT id, date, location, task, person, category, 
                              datetime(created_at, 'localtime') as created_at
                       FROM field_schedules
                       WHERE date >= ?
                       ORDER BY created_at DESC \
                       """

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                # row_factory를 sqlite3.Row로 설정하면 결과를 튜플이 아닌 딕셔너리처럼 다룰 수 있음
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(select_query, (target_date,))
                rows = cursor.fetchall()

                # sqlite3.Row 객체들을 일반 파이썬 딕셔너리 리스트로 변환하여 반환
                result = [dict(row) for row in rows]

            logger.info(f"[{target_date}] 일정 조회 완료 (총 {len(result)}건)")
            return result

        except sqlite3.Error as e:
            logger.error(f"[DB 에러] 일정 Select 중 오류 발생: {e}")
            return []


# 테스트용 코드
if __name__ == "__main__":
    db = DBManager("test_schedule.db")

    # 1. AI 파싱 결과(가정) Insert 테스트
    sample_parsed_data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "location": "안양 현장",
        "task": "접지 완료",
        "person": "김대리",
        "category": "작업완료"
    }

    new_id = db.insert_schedule(sample_parsed_data)
    print(f"새로 추가된 데이터 ID: {new_id}")

    # 2. 오늘자 데이터 Select 테스트
    todays_data = db.get_todays_schedules()
    print("\n--- 오늘자 현장 일정 상황판 ---")
    for row in todays_data:
        print(row)