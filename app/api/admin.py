import csv
import io
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.auth import require_admin
from app.core.config import settings
from app.db.repos.schedule import ScheduleRepository
from app.db.repos.admin import AdminRepository
from app.db.repos.worker import WorkerRepository
from app.db.repos.user import UserRepository
from app.db.repos.export import ExportRepository
from app.db.repos.monthly_progress import MonthlyProgressRepository
from app.db.repos.usage_metrics import UsageMetricsRepository
from app.db.deps import (
    get_schedule_repo,
    get_admin_repo,
    get_worker_repo,
    get_user_repo,
    get_export_repo,
    get_monthly_progress_repo,
    get_usage_metrics_repo,
)
from app.services.export_service import DailyExportService
from app.services.erp_sync_service import sync_constructions
from app.api.schedules import reload_construction_list


router = APIRouter(prefix="/api/admin", tags=["Admin"])


class ReviewRequest(BaseModel):
    request_id: int = Field(..., description="관리자 요청 ID")
    decision: str = Field(..., description="approve 또는 reject")
    schedule_id: Optional[int] = Field(default=None, description="수정/삭제 대상 일정 ID")
    schedule_data: Optional[Dict[str, Any]] = Field(default=None, description="수정 내용")
    reason: str = Field(default="", description="반려/삭제 사유")


class DailyExportRequest(BaseModel):
    target_date: Optional[str] = Field(default=None, description="YYYY-MM-DD, 없으면 어제")


class FieldStaffCreate(BaseModel):
    name: str = Field(..., min_length=1, description="현장직 이름")
    sort_order: int = Field(default=0, description="정렬 순서")


class FieldStaffColorUpdate(BaseModel):
    color: str = Field(..., pattern=r"^#[0-9a-fA-F]{6}$", description="담당자 카드 색상 (#RRGGBB)")


class FrequentSiteCreate(BaseModel):
    title: str = Field(..., min_length=1, description="사이트 이름")
    url: str = Field(..., min_length=1, description="사이트 URL")
    sort_order: int = Field(default=0, description="정렬 순서")


class LoginAccessReviewRequest(BaseModel):
    decision: str = Field(..., description="approve 또는 reject")
    role: str = Field(default="worker", description="approve 시 부여할 역할(admin/worker)")
    note: str = Field(default="", description="관리자 메모")


class MonthlyProgressConfigSave(BaseModel):
    month: str = Field(..., min_length=7, max_length=7, description="YYYY-MM")
    label: str = Field(default="", description="표시 월 라벨")
    total_progress: float = Field(default=34.8, ge=0, le=100, description="총 공정률")
    target_amount_thousand: int = Field(default=429250, ge=0, description="목표금액(천원)")


def _usage_metrics_range(date_from: str, date_to: str) -> tuple[str, str]:
    try:
        today = datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()
    except Exception:
        today = date.today()
    try:
        start = date.fromisoformat(date_from) if date_from else today - timedelta(days=27)
        end = date.fromisoformat(date_to) if date_to else today
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD 이어야 합니다.")
    if start > end:
        raise HTTPException(status_code=400, detail="date_from은 date_to보다 늦을 수 없습니다.")
    if (end - start).days > 366:
        raise HTTPException(status_code=400, detail="한 번에 조회할 수 있는 기간은 최대 367일입니다.")
    return start.isoformat(), end.isoformat()


def _usage_metrics_payload(
    usage_repo: UsageMetricsRepository,
    date_from: str,
    date_to: str,
) -> Dict[str, Any]:
    start, end = _usage_metrics_range(date_from, date_to)
    metrics = usage_repo.get_usage_metrics(start, end)
    return {
        "period": {"date_from": start, "date_to": end},
        **metrics,
        "definitions": {
            "active_user": "로그인 상태로 화면을 열었거나 일정 신규·수정·삭제를 수행한 고유 사용자",
            "activity_day": "한 명 이상의 실사용자가 활동한 날짜",
            "schedule_created": "DB에 새 일정 행이 실제 삽입된 건수",
            "schedule_updated": "일정 내용 변경이 DB에 실제 반영된 건수(정렬·확인 처리는 제외)",
            "schedule_deleted": "일정이 실제 소프트 삭제된 건수",
        },
    }


@router.get("/requests")
def list_requests(
    status: str = "pending",
    requested_by: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    _admin=Depends(require_admin),
    admin_repo: AdminRepository = Depends(get_admin_repo),
):
    return {
        "status": "success",
        "data": admin_repo.list_requests(status=status, requested_by=requested_by, since=since, until=until),
    }


@router.get("/audit-events")
def list_audit_events(
    limit: int = 200,
    actions: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    _admin=Depends(require_admin),
    admin_repo: AdminRepository = Depends(get_admin_repo),
):
    action_list = [a.strip() for a in (actions or "").split(",") if a.strip()]
    return {
        "status": "success",
        "data": admin_repo.list_audit_events(limit=limit, actions=action_list or None, since=since, until=until),
    }


@router.get("/usage-metrics", summary="실사용자 및 일정 변경 운영지표")
def get_usage_metrics(
    date_from: str = "",
    date_to: str = "",
    _admin=Depends(require_admin),
    usage_repo: UsageMetricsRepository = Depends(get_usage_metrics_repo),
):
    return {
        "status": "success",
        "data": _usage_metrics_payload(usage_repo, date_from, date_to),
    }


@router.get("/usage-metrics.csv", summary="실사용자 및 일정 변경 운영지표 CSV")
def export_usage_metrics_csv(
    date_from: str = "",
    date_to: str = "",
    grain: Literal["weekly", "daily"] = "weekly",
    _admin=Depends(require_admin),
    usage_repo: UsageMetricsRepository = Depends(get_usage_metrics_repo),
):
    data = _usage_metrics_payload(usage_repo, date_from, date_to)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    if grain == "weekly":
        writer.writerow([
            "week_start",
            "week_end",
            "weekly_active_users",
            "activity_days",
            "schedule_created_count",
            "schedule_update_count",
            "schedule_delete_count",
        ])
        for row in data["weekly"]:
            writer.writerow([
                row["week_start"],
                row["week_end"],
                row["weekly_active_users"],
                row["activity_days"],
                row["schedule_created_count"],
                row["schedule_update_count"],
                row["schedule_delete_count"],
            ])
    else:
        writer.writerow([
            "date",
            "active_users",
            "schedule_created_count",
            "schedule_update_count",
            "schedule_delete_count",
        ])
        for row in data["daily"]:
            writer.writerow([
                row["date"],
                row["active_users"],
                row["schedule_created_count"],
                row["schedule_update_count"],
                row["schedule_delete_count"],
            ])

    filename = f"usage_metrics_{data['period']['date_from']}_{data['period']['date_to']}_{grain}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/requests/{request_id}/candidates")
def recommend_candidates(
    request_id: int,
    _admin=Depends(require_admin),
    admin_repo: AdminRepository = Depends(get_admin_repo),
    sched_repo: ScheduleRepository = Depends(get_schedule_repo),
):
    row = admin_repo.get_request_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다.")

    target_date = None
    target_keyword = None
    payload_json = row.get("payload_json") or ""
    if payload_json:
        try:
            parsed = json.loads(payload_json)
            target_date = parsed.get("target_date")
            target_keyword = parsed.get("target_keyword")
            if not target_keyword and isinstance(parsed.get("schedule_data"), dict):
                target_keyword = parsed["schedule_data"].get("location") or parsed["schedule_data"].get("task")
        except Exception:
            pass

    text = (row.get("request_text") or "").strip()
    keywords = []
    if target_keyword:
        keywords.append(target_keyword)
    if text:
        tokens = [t for t in re.split(r"\s+", text) if len(t) >= 2]
        noise = {"수정", "삭제", "요청", "해주세요", "해줘", "일정", "등록", "메모", "관련", "처리"}
        for t in tokens:
            if t not in noise and t not in keywords:
                keywords.append(t)

    merged: Dict[int, Dict[str, Any]] = {}
    if not keywords:
        for item in sched_repo.search_by_keyword(date=target_date, keyword=None)[:20]:
            merged[item["id"]] = item
    else:
        for kw in keywords[:6]:
            for item in sched_repo.search_by_keyword(date=target_date, keyword=kw):
                merged[item["id"]] = item
            if len(merged) >= 20:
                break

    return {
        "status": "success",
        "hint": {"target_date": target_date, "target_keyword": target_keyword, "keywords": keywords[:6]},
        "data": list(merged.values())[:20],
    }


@router.post("/requests/review")
def review_request(
    payload: ReviewRequest,
    background_tasks: BackgroundTasks,
    admin=Depends(require_admin),
    admin_repo: AdminRepository = Depends(get_admin_repo),
    sched_repo: ScheduleRepository = Depends(get_schedule_repo),
    usage_repo: UsageMetricsRepository = Depends(get_usage_metrics_repo),
):
    request_row = admin_repo.get_request_by_id(payload.request_id)
    if not request_row:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다.")
    if request_row["status"] != "pending":
        raise HTTPException(status_code=400, detail="이미 처리된 요청입니다.")

    if payload.decision == "reject":
        admin_repo.update_request_status(payload.request_id, "rejected")
        return {"status": "success", "message": "요청을 반려했습니다."}

    if payload.decision != "approve":
        raise HTTPException(status_code=400, detail="decision 값이 올바르지 않습니다.")

    request_type = request_row.get("request_type", "")
    applied = False

    payload_data = payload.schedule_data
    if payload_data is None and request_row.get("payload_json"):
        try:
            parsed = json.loads(request_row["payload_json"])
            payload_data = parsed.get("schedule_data") if isinstance(parsed, dict) else None
            if payload.schedule_id is None and isinstance(parsed, dict):
                payload.schedule_id = parsed.get("schedule_id")
        except Exception:
            payload_data = None

    actor_user = admin["user_id"]
    actor_device = admin.get("device_name", "admin-device")

    if request_type in ["update_request"] and payload.schedule_id and payload_data:
        applied = sched_repo.update_by_id(payload.schedule_id, payload_data, actor_user=actor_user, actor_device=actor_device)
        if applied:
            usage_repo.record_schedule_event(
                event_type="schedule_updated",
                actor_user=actor_user,
                actor_device=actor_device,
                schedule_id=payload.schedule_id,
                source="admin_review",
            )
            updated = sched_repo.get_by_id(payload.schedule_id)
            if updated and str(updated.get("work_code") or "").strip():
                background_tasks.add_task(sync_constructions, [updated])
    elif request_type in ["delete_request"] and payload.schedule_id:
        applied = sched_repo.soft_delete(schedule_id=payload.schedule_id, deleted_by=actor_user,
                                          delete_reason=payload.reason, actor_device=actor_device)
        if applied:
            usage_repo.record_schedule_event(
                event_type="schedule_deleted",
                actor_user=actor_user,
                actor_device=actor_device,
                schedule_id=payload.schedule_id,
                source="admin_review",
            )
    elif request_type in ["other", "update_request", "delete_request", "unclassified"]:
        applied = True
    else:
        applied = True

    admin_repo.update_request_status(payload.request_id, "approved" if applied else "failed")
    if not applied:
        raise HTTPException(status_code=400, detail="요청 적용에 실패했습니다. 데이터 확인이 필요합니다.")
    return {"status": "success", "message": "요청이 승인 처리되었습니다."}


@router.post("/erp-sync", summary="ERP 서버로 공사 일괄 동기화")
def erp_bulk_sync(
    date_from: str = "2026-06-01",
    date_to: Optional[str] = None,
    _admin=Depends(require_admin),
    sched_repo: ScheduleRepository = Depends(get_schedule_repo),
):
    """
    work_code가 있는 공사를 지정 기간 범위로 ERP에 일괄 전송한다.
    date_to 미지정 시 오늘 이전까지.
    """
    from datetime import date as _date
    end = date_to or _date.today().strftime("%Y-%m-%d")
    rows = sched_repo.list_by_date_range(date_from, end)
    records = [
        r for r in rows
        if str(r.get("work_code") or "").strip()
    ]
    if not records:
        return {"status": "success", "message": "전송할 공사가 없습니다.", "sent": 0}

    sync_constructions(records)
    return {
        "status": "success",
        "message": f"{len(records)}건을 ERP로 전송했습니다.",
        "sent": len(records),
        "date_from": date_from,
        "date_to": end,
    }


@router.get("/login-access-requests")
def list_login_access_requests(
    status: str = "pending",
    _admin=Depends(require_admin),
    user_repo: UserRepository = Depends(get_user_repo),
):
    return {"status": "success", "data": user_repo.list_login_access_requests(status=status)}


@router.post("/login-access-requests/{request_id}/review")
def review_login_access_request(
    request_id: int,
    payload: LoginAccessReviewRequest,
    admin=Depends(require_admin),
    user_repo: UserRepository = Depends(get_user_repo),
):
    try:
        reviewed = user_repo.review_login_access_request(
            request_id=request_id, decision=payload.decision,
            reviewed_by=admin["user_id"], role=payload.role, note=payload.note,
        )
        if reviewed.get("status") == "approved":
            user_repo.ensure_oauth_user(
                user_id=str(reviewed.get("user_id") or f"kakao_{reviewed.get('kakao_id', '')}"),
                user_name=str(reviewed.get("user_name") or f"kakao_{reviewed.get('kakao_id', '')}"),
                role=str(reviewed.get("role") or "worker"),
            )
        return {"status": "success", "data": reviewed}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/field-staff")
def add_field_staff(
    payload: FieldStaffCreate,
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    try:
        new_id = worker_repo.add_field_staff(payload.name.strip(), payload.sort_order)
        return {"status": "success", "id": new_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 등록된 이름입니다.")


@router.delete("/field-staff/{staff_id}")
def delete_field_staff(
    staff_id: int,
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    if not worker_repo.delete_field_staff(staff_id):
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제되었습니다."}


@router.put("/field-staff/{staff_id}/color")
def update_field_staff_color(
    staff_id: int,
    payload: FieldStaffColorUpdate,
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    try:
        updated = worker_repo.update_field_staff_color(staff_id, payload.color)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    return {"status": "success", "data": updated}


@router.post("/outing-staff")
def add_outing_staff(
    payload: FieldStaffCreate,
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    try:
        new_id = worker_repo.add_outing_staff(payload.name.strip(), payload.sort_order)
        return {"status": "success", "id": new_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 등록된 이름입니다.")


@router.delete("/outing-staff/{staff_id}")
def delete_outing_staff(
    staff_id: int,
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    if not worker_repo.delete_outing_staff(staff_id):
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제되었습니다."}


@router.get("/frequent-sites")
def list_frequent_sites(
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    return {"status": "success", "data": worker_repo.list_frequent_sites()}


@router.post("/frequent-sites")
def add_frequent_site(
    payload: FrequentSiteCreate,
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    try:
        new_id = worker_repo.add_frequent_site(title=payload.title.strip(), url=payload.url.strip(), sort_order=payload.sort_order)
        return {"status": "success", "id": new_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 등록된 URL입니다.")


@router.delete("/frequent-sites/{site_id}")
def delete_frequent_site(
    site_id: int,
    _admin=Depends(require_admin),
    worker_repo: WorkerRepository = Depends(get_worker_repo),
):
    if not worker_repo.delete_frequent_site(site_id):
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제되었습니다."}


@router.get("/monthly-progress-config")
def admin_get_monthly_progress_config(
    month: str = "",
    _admin=Depends(require_admin),
    repo: MonthlyProgressRepository = Depends(get_monthly_progress_repo),
):
    return {"status": "success", "data": repo.get_config(month or None)}


@router.put("/monthly-progress-config")
def admin_save_monthly_progress_config(
    payload: MonthlyProgressConfigSave,
    admin=Depends(require_admin),
    repo: MonthlyProgressRepository = Depends(get_monthly_progress_repo),
):
    try:
        saved = repo.upsert_config(
            month=payload.month,
            label=payload.label,
            total_progress=payload.total_progress,
            target_amount_thousand=payload.target_amount_thousand,
            updated_by=admin.get("user_id", "admin"),
        )
        return {"status": "success", "data": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/export/daily")
def run_daily_export(
    payload: DailyExportRequest,
    _admin=Depends(require_admin),
    export_repo: ExportRepository = Depends(get_export_repo),
):
    from app.db.deps import get_db_path
    db_path = get_db_path()
    target_date = payload.target_date or DailyExportService.yesterday_str()
    svc = DailyExportService(db_path=db_path)
    try:
        result = svc.export_date(target_date)
        archive = svc.archive_old_daily_reports(keep_days=90)
        return {
            "status": "success",
            "message": "백업 데이터 생성이 완료되었습니다.",
            "data": result,
            "archive": archive,
        }
    except Exception as e:
        export_repo.create_export_job(target_date=target_date, status="failed", output_path="", message=str(e))
        raise HTTPException(status_code=500, detail=f"일일 내보내기 실패: {e}")


@router.post("/reload-construction-list", summary="수주대장 자동완성 캐시 강제 리로드")
def reload_construction_list_endpoint(
    _admin=Depends(require_admin),
):
    count = reload_construction_list()
    return {"status": "success", "message": f"수주대장 {count}건 리로드 완료"}
