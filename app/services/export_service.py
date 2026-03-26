from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from app.db.db_manager import DBManager


class DailyExportService:
    def __init__(self, db: DBManager, base_path: str = "자동화_데이터/일일백업"):
        self.db = db
        self.base = Path(base_path)

    def export_date(self, target_date: str) -> Dict[str, Any]:
        schedules = self.db.get_daily_schedules(target_date)
        memos = self.db.get_daily_memos(target_date)
        statuses = self.db.list_worker_status()

        target_dir = self.base / target_date
        target_dir.mkdir(parents=True, exist_ok=True)

        schedule_path = target_dir / "공사일정.xlsx"
        memo_path = target_dir / "기타메모.xlsx"
        status_path = target_dir / "인원상태.xlsx"

        pd.DataFrame(schedules).to_excel(schedule_path, index=False)
        pd.DataFrame(memos).to_excel(memo_path, index=False)
        pd.DataFrame(statuses).to_excel(status_path, index=False)

        self.db.create_export_job(
            target_date=target_date,
            status="success",
            output_path=str(target_dir),
            message=f"schedules={len(schedules)}, memos={len(memos)}, status={len(statuses)}",
        )
        return {
            "target_date": target_date,
            "output_dir": str(target_dir),
            "counts": {
                "schedules": len(schedules),
                "memos": len(memos),
                "statuses": len(statuses),
            },
        }

    def export_yesterday_if_needed(self) -> Dict[str, Any]:
        target_date = self.yesterday_str()
        if self.db.has_success_export(target_date):
            return {"target_date": target_date, "skipped": True, "reason": "already_exported"}
        result = self.export_date(target_date)
        result["skipped"] = False
        return result

    @staticmethod
    def yesterday_str() -> str:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
