# app/db/repos/monthly_progress.py
from datetime import date
from typing import Any, Dict, Optional

from app.db.connection import get_conn


DEFAULT_TOTAL_PROGRESS = 34.8
DEFAULT_TARGET_AMOUNT_THOUSAND = 429250


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
                SELECT month, label, total_progress, target_amount_thousand, updated_by,
                       datetime(updated_at,'localtime') AS updated_at,
                       COALESCE(target_image_name,'') AS target_image_name,
                       datetime(target_image_updated_at,'localtime') AS target_image_updated_at
                FROM monthly_progress_config
                WHERE month=?
                """,
                (key,),
            ).fetchone()
        if row:
            cfg = dict(row)
            cfg["target_image_updated_at"] = cfg.get("target_image_updated_at") or ""
            return cfg
        return {
            "month": key,
            "label": month_label(key) or "6월",
            "total_progress": DEFAULT_TOTAL_PROGRESS,
            "target_amount_thousand": DEFAULT_TARGET_AMOUNT_THOUSAND,
            "updated_by": "",
            "updated_at": "",
            "target_image_name": "",
            "target_image_updated_at": "",
        }

    def set_target_image(self, month: str, image_name: str) -> Dict[str, Any]:
        """
        월간 목표 이미지 파일명을 기록한다. 이 행이 아직 없으면 기본값으로 만들어 둔다 —
        목표금액을 안 정한 달에도 이미지부터 올릴 수 있어야 하기 때문.
        """
        key = (month or "").strip()
        if not key:
            raise ValueError("month is required.")
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO monthly_progress_config
                    (month, label, total_progress, target_amount_thousand,
                     target_image_name, target_image_updated_at)
                    VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(month) DO UPDATE SET
                        target_image_name=excluded.target_image_name,
                        target_image_updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        key,
                        month_label(key) or key,
                        DEFAULT_TOTAL_PROGRESS,
                        DEFAULT_TARGET_AMOUNT_THOUSAND,
                        (image_name or "").strip(),
                    ),
                )
        return self.get_config(key)

    def clear_target_image(self, month: str) -> Dict[str, Any]:
        key = (month or "").strip()
        if not key:
            raise ValueError("month is required.")
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    "UPDATE monthly_progress_config"
                    " SET target_image_name='', target_image_updated_at=NULL WHERE month=?",
                    (key,),
                )
        return self.get_config(key)

    def upsert_config(
        self,
        month: str,
        label: str,
        total_progress: float,
        target_amount_thousand: int,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        key = (month or "").strip()
        if not key:
            raise ValueError("month is required.")
        safe_label = (label or "").strip() or month_label(key) or key
        progress = max(0.0, min(100.0, float(total_progress)))
        target = max(0, int(target_amount_thousand))
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO monthly_progress_config
                    (month, label, total_progress, target_amount_thousand, updated_by, updated_at)
                    VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(month) DO UPDATE SET
                        -- 이미지 컬럼은 일부러 빼둔다. 목표금액을 고치는 저장이 이미지를 지우면
                        -- 사용자는 숫자만 바꿨는데 그림이 사라진다(폼 저장=전체 덮어쓰기 사고).
                        label=excluded.label,
                        total_progress=excluded.total_progress,
                        target_amount_thousand=excluded.target_amount_thousand,
                        updated_by=excluded.updated_by,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (key, safe_label, progress, target, updated_by),
                )
        return self.get_config(key)
