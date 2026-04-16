from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
import zipfile

import pandas as pd

from app.db.db_manager import DBManager


class DailyExportService:
    def __init__(self, db: DBManager, base_path: str = "자동화_데이터"):
        self.db = db # DB 초기화
        self.base = Path(base_path) # 기본 경로 초기화

    def export_date(self, target_date: str) -> Dict[str, Any]:
        schedules = self.db.get_daily_schedules(target_date) # 일일 일정 조회
        all_schedules = self.db.get_all_schedules_for_backup() # 전체 공사 이력 조회
        statuses = self.db.list_worker_status() # 일일 상태 조회
        admin_requests = self.db.get_daily_admin_requests(target_date) # 관리자 요청
        audit_events = self.db.get_daily_audit_events(target_date) # 변경 이력
        login_sessions = self.db.get_daily_login_sessions(target_date) # 로그인 세션
        chat_events = self.db.get_daily_chat_events(target_date) # 채팅 로그
        metrics = self.db.get_daily_backup_metrics(target_date) # 일간 운영 지표

        self.base.mkdir(parents=True, exist_ok=True) # 기본 경로 생성
        workbook_path = self.base / f"{target_date}_백업데이터.xlsx"

        def with_deleted_flag(rows):
            out = []
            for row in rows:
                copied = dict(row)
                copied["is_deleted"] = "Y" if str(copied.get("deleted_at", "") or "").strip() else "N"
                out.append(copied)
            return out

        schedules_with_flag = with_deleted_flag(schedules)
        all_schedules_with_flag = with_deleted_flag(all_schedules)

        with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
            # 1) 핵심 데이터(우선순위 최고)
            pd.DataFrame(schedules_with_flag).to_excel(writer, sheet_name="공사일정_당일", index=False)
            pd.DataFrame(all_schedules_with_flag).to_excel(writer, sheet_name="공사일정_전체", index=False)
            core_cols = [
                "id", "date", "location", "task", "details", "person", "tags", "category", "is_deleted",
                "deleted_at", "deleted_by", "delete_reason", "last_actor_user", "last_actor_at", "created_at"
            ]
            core_rows = [{k: row.get(k, "") for k in core_cols} for row in all_schedules_with_flag]
            pd.DataFrame(core_rows).to_excel(writer, sheet_name="공사일정_핵심", index=False)

            # 2) 운영 보조 데이터
            status_rows = []
            for row in statuses:
                copied = dict(row)
                copied["exported_date"] = target_date
                status_rows.append(copied)
            pd.DataFrame(status_rows).to_excel(writer, sheet_name="외출상태_스냅샷", index=False)
            pd.DataFrame(admin_requests).to_excel(writer, sheet_name="관리자요청", index=False)
            pd.DataFrame(audit_events).to_excel(writer, sheet_name="감사로그", index=False)
            pd.DataFrame(login_sessions).to_excel(writer, sheet_name="로그인세션", index=False)
            pd.DataFrame(chat_events).to_excel(writer, sheet_name="채팅로그", index=False)

            # 3) 커리어/비즈니스 성과 증빙용 지표
            metrics_rows = [{"metric": key, "value": value} for key, value in metrics.items()]
            pd.DataFrame(metrics_rows).to_excel(writer, sheet_name="운영지표", index=False)

        self.db.create_export_job(
            target_date=target_date, # 타겟 날짜 초기화
            status="success", # 상태 초기화
            output_path=str(workbook_path), # 출력 경로 초기화
            message=(
                f"schedules={len(schedules)}, status={len(statuses)}, "
                f"dau={metrics.get('daily_active_user_count', 0)}, chat={metrics.get('chat_count', 0)}"
            ), # 메시지 초기화
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
        targets_by_month: Dict[str, list[Path]] = {}
        all_month_keys = set()
        for file_path in self.base.glob("*_백업데이터.xlsx"):
            name = file_path.name
            try:
                report_date = datetime.strptime(name[:10], "%Y-%m-%d").date()
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

        # 권장 정책: 일 단위가 아닌 월 단위(완료 월)로 한 번에 압축
        # 즉, 해당 월의 마지막 날짜가 cutoff를 지난 경우에만 그 월 파일 전체를 압축한다.
        expired_months = set()
        for month_key in all_month_keys:
            month_end = month_end_date(month_key)
            if month_end and month_end <= cutoff:
                expired_months.add(month_key)

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

        return {
            "keep_days": keep_days,
            "archived_count": archived_count,
            "deleted_count": deleted_count,
            "months": len(expired_months),
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
