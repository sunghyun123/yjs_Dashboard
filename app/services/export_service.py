from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
import zipfile

import pandas as pd

from app.db.repos.schedule import ScheduleRepository
from app.db.repos.admin import AdminRepository
from app.db.repos.worker import WorkerRepository
from app.db.repos.export import ExportRepository
from app.core.config import settings


class DailyExportService:
    def __init__(self, db_path: str, base_path: str = ""):
        self._db_path = db_path
        self.base = Path(base_path or settings.UPLOADS_DIR)

    def export_date(self, target_date: str) -> Dict[str, Any]:
        sched = ScheduleRepository(self._db_path)
        admin = AdminRepository(self._db_path)
        worker = WorkerRepository(self._db_path)
        export = ExportRepository(self._db_path)

        schedules = sched.list_by_date(target_date)
        all_schedules = sched.list_all_for_backup()
        statuses = worker.list_status()
        admin_requests = admin.list_daily_requests(target_date)
        audit_events = admin.list_daily_audit_events(target_date)
        login_sessions = ScheduleRepository(self._db_path)  # placeholder
        from app.db.repos.user import UserRepository
        login_sessions = UserRepository(self._db_path).list_daily_sessions(target_date)
        chat_events = admin.list_daily_chat_events(target_date)
        metrics = export.get_daily_metrics(target_date)

        self.base.mkdir(parents=True, exist_ok=True)
        workbook_path = self.base / f"{target_date}_백업데이터.xlsx"

        def with_deleted_flag(rows):
            out = []
            for row in rows:
                copied = dict(row)
                copied["is_deleted"] = "Y" if str(copied.get("deleted_at", "") or "").strip() else "N"
                out.append(copied)
            return out

        schedules_flagged = with_deleted_flag(schedules)
        all_flagged = with_deleted_flag(all_schedules)

        with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
            pd.DataFrame(schedules_flagged).to_excel(writer, sheet_name="공사일정_당일", index=False)
            pd.DataFrame(all_flagged).to_excel(writer, sheet_name="공사일정_전체", index=False)
            core_cols = [
                "id", "date", "location", "task", "details", "person", "tags", "category", "is_deleted",
                "deleted_at", "deleted_by", "delete_reason", "last_actor_user", "last_actor_at", "created_at",
            ]
            core_rows = [{k: row.get(k, "") for k in core_cols} for row in all_flagged]
            pd.DataFrame(core_rows).to_excel(writer, sheet_name="공사일정_핵심", index=False)

            status_rows = [{**dict(row), "exported_date": target_date} for row in statuses]
            pd.DataFrame(status_rows).to_excel(writer, sheet_name="외출상태_스냅샷", index=False)
            pd.DataFrame(admin_requests).to_excel(writer, sheet_name="관리자요청", index=False)
            pd.DataFrame(audit_events).to_excel(writer, sheet_name="감사로그", index=False)
            pd.DataFrame(login_sessions).to_excel(writer, sheet_name="로그인세션", index=False)
            pd.DataFrame(chat_events).to_excel(writer, sheet_name="채팅로그", index=False)

            metrics_rows = [{"metric": k, "value": v} for k, v in metrics.items()]
            pd.DataFrame(metrics_rows).to_excel(writer, sheet_name="운영지표", index=False)

        export.create_export_job(
            target_date=target_date,
            status="success",
            output_path=str(workbook_path),
            message=(
                f"schedules={len(schedules)}, status={len(statuses)}, "
                f"dau={metrics.get('daily_active_user_count', 0)}, chat={metrics.get('chat_count', 0)}"
            ),
        )
        return {
            "target_date": target_date,
            "output_file": str(workbook_path),
            "counts": {
                "schedules_daily": len(schedules),
                "schedules_all": len(all_schedules),
                "statuses": len(statuses),
                "admin_requests": len(admin_requests),
                "audit_events": len(audit_events),
                "login_sessions": len(login_sessions),
                "chat_events": len(chat_events),
                "daily_active_users": metrics.get("daily_active_user_count", 0),
                "chat_count": metrics.get("chat_count", 0),
            },
        }

    def archive_old_daily_reports(self, keep_days: int = 30) -> Dict[str, Any]:
        self.base.mkdir(parents=True, exist_ok=True)
        archives_dir = self.base / "archives"
        archives_dir.mkdir(parents=True, exist_ok=True)
        cutoff = datetime.now().date() - timedelta(days=keep_days)
        targets_by_month: Dict[str, list] = {}
        all_month_keys = set()
        for file_path in self.base.glob("*_백업데이터.xlsx"):
            name = file_path.name
            try:
                datetime.strptime(name[:10], "%Y-%m-%d")
            except ValueError:
                continue
            month_key = name[:7]
            all_month_keys.add(month_key)
            targets_by_month.setdefault(month_key, []).append(file_path)

        def month_end_date(month_key: str):
            try:
                first_day = datetime.strptime(f"{month_key}-01", "%Y-%m-%d").date()
            except ValueError:
                return None
            if first_day.month == 12:
                next_month = first_day.replace(year=first_day.year + 1, month=1, day=1)
            else:
                next_month = first_day.replace(month=first_day.month + 1, day=1)
            return next_month - timedelta(days=1)

        expired_months = {
            mk for mk in all_month_keys
            if (end := month_end_date(mk)) and end <= cutoff
        }

        archived_count = 0
        deleted_count = 0
        for month_key, files in targets_by_month.items():
            if month_key not in expired_months:
                continue
            zip_path = archives_dir / f"{month_key}_백업데이터.zip"
            with zipfile.ZipFile(zip_path, mode="a", compression=zipfile.ZIP_DEFLATED) as zipf:
                existing = set(zipf.namelist())
                for file_path in sorted(files):
                    if file_path.name not in existing:
                        zipf.write(file_path, arcname=file_path.name)
                        archived_count += 1
            for file_path in files:
                if file_path.exists():
                    file_path.unlink()
                    deleted_count += 1

        return {"keep_days": keep_days, "archived_count": archived_count,
                "deleted_count": deleted_count, "months": len(expired_months)}

    def export_yesterday_if_needed(self) -> Dict[str, Any]:
        target_date = self.yesterday_str()
        if ExportRepository(self._db_path).has_success_export(target_date):
            return {"target_date": target_date, "skipped": True, "reason": "already_exported"}
        result = self.export_date(target_date)
        result["skipped"] = False
        return result

    @staticmethod
    def yesterday_str() -> str:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
