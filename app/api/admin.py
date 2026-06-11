import json
import re
import sqlite3
from typing import Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import require_admin
from app.core.config import settings
from app.db.repos.schedule import ScheduleRepository
from app.db.repos.admin import AdminRepository
from app.db.repos.worker import WorkerRepository
from app.db.repos.user import UserRepository
from app.db.repos.export import ExportRepository
from app.db.deps import get_schedule_repo, get_admin_repo, get_worker_repo, get_user_repo, get_export_repo
from app.services.export_service import DailyExportService
from app.services.erp_sync_service import sync_constructions


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


class FrequentSiteCreate(BaseModel):
    title: str = Field(..., min_length=1, description="사이트 이름")
    url: str = Field(..., min_length=1, description="사이트 URL")
    sort_order: int = Field(default=0, description="정렬 순서")


class LoginAccessReviewRequest(BaseModel):
    decision: str = Field(..., description="approve 또는 reject")
    role: str = Field(default="worker", description="approve 시 부여할 역할(admin/worker)")
    note: str = Field(default="", description="관리자 메모")


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
            updated = sched_repo.get_by_id(payload.schedule_id)
            if updated and str(updated.get("work_code") or "").strip():
                background_tasks.add_task(sync_constructions, [updated])
    elif request_type in ["delete_request"] and payload.schedule_id:
        applied = sched_repo.soft_delete(schedule_id=payload.schedule_id, deleted_by=actor_user,
                                          delete_reason=payload.reason, actor_device=actor_device)
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
