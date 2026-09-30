# app/db/repos/monthly_progress.py
from datetime import date
from typing import Any, Dict, List, Optional

from app.db.connection import get_conn


DEFAULT_TOTAL_PROGRESS = 34.8

TARGET_KINDS = ("construction", "settlement")


def current_month_key() -> str:
    return date.today().strftime("%Y-%m")


def month_label(month: str) -> str:
    try:
        return f"{int(str(month).split('-')[1])}월"
    except Exception:
        return ""


class MonthlyProgressRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def get_config(self, month: Optional[str] = None) -> Dict[str, Any]:
        key = (month or current_month_key()).strip()
        with get_conn(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT month, label, total_progress, updated_by,
                       datetime(updated_at,'localtime') AS updated_at
                FROM monthly_progress_config
                WHERE month=?
                """,
                (key,),
            ).fetchone()
        cfg = dict(row) if row else {
            "month": key,
            "label": month_label(key) or "6월",
            "total_progress": DEFAULT_TOTAL_PROGRESS,
            "updated_by": "",
            "updated_at": "",
        }
        # 목표 총액은 여기서 합산해 보내지 않는다. 행만 보내고 화면이 행에서 합계를 만든다 —
        # 도넛 분모와 목표 상세 표의 합계가 같은 배열에서 나와야 둘이 갈라질 자리가 없다.
        cfg["targets"] = self.list_target_rows(key)
        return cfg

    def list_target_rows(self, month: str) -> Dict[str, List[Dict[str, Any]]]:
        key = (month or "").strip()
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, kind, jijung_no, name, amount_thousand
                FROM monthly_target_rows
                WHERE month=?
                ORDER BY id
                """,
                (key,),
            ).fetchall()
        grouped: Dict[str, List[Dict[str, Any]]] = {kind: [] for kind in TARGET_KINDS}
        for r in rows:
            grouped[r["kind"]].append({
                "id": r["id"],
                "jijungNo": r["jijung_no"],
                "name": r["name"],
                "amountThousand": r["amount_thousand"],
            })
        return grouped

    def add_target_row(
        self,
        month: str,
        kind: str,
        jijung_no: str,
        name: str,
        amount_thousand: int,
        created_by: str = "",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """행 하나를 추가하고 그 달의 목표 행 전체를 돌려준다.

        같은 달·같은 종류·같은 지중No가 이미 있으면 sqlite3.IntegrityError 가 올라간다(호출부가 409로 바꾼다).
        """
        if kind not in TARGET_KINDS:
            raise ValueError("kind must be construction or settlement.")
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO monthly_target_rows
                    (month, kind, jijung_no, name, amount_thousand, created_by)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (month, kind, jijung_no.strip(), name.strip(), int(amount_thousand), created_by),
                )
        return self.list_target_rows(month)

    def delete_target_row(self, row_id: int) -> Optional[str]:
        """지운 행의 month 를 돌려준다. 없는 id 면 None."""
        with get_conn(self._db_path) as conn:
            with conn:
                row = conn.execute(
                    "SELECT month FROM monthly_target_rows WHERE id=?", (row_id,)
                ).fetchone()
                if not row:
                    return None
                conn.execute("DELETE FROM monthly_target_rows WHERE id=?", (row_id,))
        return row["month"]

    def upsert_config(
        self,
        month: str,
        label: str,
        total_progress: float,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        key = (month or "").strip()
        if not key:
            raise ValueError("month is required.")
        safe_label = (label or "").strip() or month_label(key) or key
        progress = max(0.0, min(100.0, float(total_progress)))
        with get_conn(self._db_path) as conn:
            with conn:
                # target_amount_thousand·target_image_* 칸은 테이블에 남아 있지만 더는 읽지도 쓰지도 않는다.
                # 목표는 monthly_target_rows 의 행 합계가 유일한 원본이다.
                conn.execute(
                    """
                    INSERT INTO monthly_progress_config
                    (month, label, total_progress, updated_by, updated_at)
                    VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(month) DO UPDATE SET
                        label=excluded.label,
                        total_progress=excluded.total_progress,
                        updated_by=excluded.updated_by,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (key, safe_label, progress, updated_by),
                )
        return self.get_config(key)
