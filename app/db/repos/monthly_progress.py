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
                       datetime(updated_at,'localtime') AS updated_at
                FROM monthly_progress_config
                WHERE month=?
                """,
                (key,),
            ).fetchone()
        if row:
            return dict(row)
        return {
            "month": key,
            "label": month_label(key) or "6월",
            "total_progress": DEFAULT_TOTAL_PROGRESS,
            "target_amount_thousand": DEFAULT_TARGET_AMOUNT_THOUSAND,
            "updated_by": "",
            "updated_at": "",
        }

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
                        label=excluded.label,
                        total_progress=excluded.total_progress,
                        target_amount_thousand=excluded.target_amount_thousand,
                        updated_by=excluded.updated_by,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (key, safe_label, progress, target, updated_by),
                )
        return self.get_config(key)
