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
        # 관리자 드롭다운과 홈 그래프 순서가 같은 목록에서 나오게 함께 보낸다
        cfg["managers"] = [m["name"] for m in self.list_managers()]
        cfg["unplannedAssignments"] = self.list_unplanned_assignments(key)
        return cfg

    # ── 담당자 목록 ──
    def list_managers(self) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute("SELECT id, name FROM target_managers ORDER BY id").fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]

    def add_manager(self, name: str) -> List[Dict[str, Any]]:
        """같은 이름이 있으면 sqlite3.IntegrityError(호출부가 409로 바꾼다)."""
        value = (name or "").strip()
        if not value:
            raise ValueError("담당자 이름을 입력하세요.")
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute("INSERT INTO target_managers (name) VALUES (?)", (value,))
        return self.list_managers()

    def delete_manager(self, manager_id: int) -> Optional[List[Dict[str, Any]]]:
        """목록에서만 지운다. 이미 목표 행·계획외 지정에 적힌 이름은 그대로 둔다 — 지난달 그래프를 보존한다."""
        with get_conn(self._db_path) as conn:
            with conn:
                cur = conn.execute("DELETE FROM target_managers WHERE id=?", (manager_id,))
        return self.list_managers() if cur.rowcount else None

    def _require_manager(self, manager: str) -> str:
        value = (manager or "").strip()
        if not value:
            raise ValueError("담당자를 선택하세요.")
        if value not in {m["name"] for m in self.list_managers()}:
            raise ValueError("등록되지 않은 담당자입니다.")
        return value

    # ── 계획외 공사 담당 지정 ──
    def list_unplanned_assignments(self, month: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT jijung_no, manager FROM monthly_unplanned_assignments WHERE month=? ORDER BY id",
                ((month or "").strip(),),
            ).fetchall()
        return [{"jijungNo": r["jijung_no"], "manager": r["manager"]} for r in rows]

    def set_unplanned_assignment(
        self, month: str, jijung_no: str, manager: str, updated_by: str = ""
    ) -> List[Dict[str, Any]]:
        """manager 가 빈 문자열이면 지정을 지운다(그 공사 실적은 다시 '계획외 실적' 줄로 간다).

        목표 행과 달리 미지정으로 되돌리는 길을 열어둔다 — 계획외 실적은 담당이 없는 상태가 정상이기도 하다.
        """
        key = (month or "").strip()
        no = (jijung_no or "").strip()
        if not no:
            raise ValueError("지중No가 없습니다.")
        value = (manager or "").strip()
        if value:
            value = self._require_manager(value)
        with get_conn(self._db_path) as conn:
            with conn:
                if not value:
                    conn.execute(
                        "DELETE FROM monthly_unplanned_assignments WHERE month=? AND jijung_no=?", (key, no)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO monthly_unplanned_assignments (month, jijung_no, manager, updated_by, updated_at)
                        VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                        ON CONFLICT(month, jijung_no) DO UPDATE SET
                            manager=excluded.manager,
                            updated_by=excluded.updated_by,
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (key, no, value, updated_by),
                    )
        return self.list_unplanned_assignments(key)

    def list_target_rows(self, month: str) -> Dict[str, List[Dict[str, Any]]]:
        key = (month or "").strip()
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, kind, jijung_no, name, amount_thousand, manager
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
                "manager": r["manager"] or "",
            })
        return grouped

    def add_target_row(
        self,
        month: str,
        kind: str,
        jijung_no: str,
        name: str,
        amount_thousand: int,
        manager: str,
        created_by: str = "",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """행 하나를 추가하고 그 달의 목표 행 전체를 돌려준다.

        같은 달·같은 종류·같은 지중No가 이미 있으면 sqlite3.IntegrityError 가 올라간다(호출부가 409로 바꾼다).
        담당자가 없거나 목록 밖이면 ValueError — 담당 없는 행은 홈 담당자별 그래프 어디에도 속하지 못한다.
        """
        if kind not in TARGET_KINDS:
            raise ValueError("kind must be construction or settlement.")
        manager = self._require_manager(manager)
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO monthly_target_rows
                    (month, kind, jijung_no, name, amount_thousand, manager, created_by)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (month, kind, jijung_no.strip(), name.strip(), int(amount_thousand), manager, created_by),
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

    def set_target_row_manager(self, row_id: int, manager: str) -> Optional[str]:
        """행의 담당자만 바꾸고 그 행의 month 를 돌려준다. 없는 id 면 None.

        금액·지중No 는 건드리지 않는다 — 담당 지정이 목표 숫자를 바꿀 자리를 남기지 않는다.
        미지정으로 되돌리는 길은 없다(추가 때와 같은 규칙). 미지정 행은 칸 추가 전에 있던 옛 행뿐이다.
        """
        value = self._require_manager(manager)
        with get_conn(self._db_path) as conn:
            with conn:
                row = conn.execute(
                    "SELECT month FROM monthly_target_rows WHERE id=?", (row_id,)
                ).fetchone()
                if not row:
                    return None
                conn.execute("UPDATE monthly_target_rows SET manager=? WHERE id=?", (value, row_id))
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
