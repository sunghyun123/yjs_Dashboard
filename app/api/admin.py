import json
import re
import sqlite3
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import require_admin
from app.core.config import settings
from app.db.db_manager import DBManager
from app.services.export_service import DailyExportService


router = APIRouter(prefix="/api/admin", tags=["Admin"])
db = DBManager(db_path=settings.sqlite_db_path)
export_svc = DailyExportService(db=db)


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


@router.get("/requests")
def list_requests(
    status: str = "pending",
    requested_by: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    _admin=Depends(require_admin),
):
    return {
        "status": "success",
        "data": db.list_admin_requests(
            status=status,
            requested_by=requested_by,
            since=since,
            until=until,
        ),
    }


@router.get("/audit-events")
def list_audit_events(
    limit: int = 200,
    actions: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    _admin=Depends(require_admin),
):
    action_list = [a.strip() for a in (actions or "").split(",") if a.strip()]
    return {
        "status": "success",
        "data": db.list_audit_events(
            limit=limit,
            actions=action_list or None,
            since=since,
            until=until,
        ),
    }


@router.get("/requests/{request_id}/candidates")
def recommend_candidates(request_id: int, _admin=Depends(require_admin)):
    row = db.get_admin_request_by_id(request_id)
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
            target_date = None
            target_keyword = None

    text = (row.get("request_text") or "").strip()

    # 키워드 후보를 여러 개 추출해 순차 검색
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
    # 키워드가 없으면 전체 최근 검색
    if not keywords:
        for row_item in db.search_schedules_by_keyword(date=target_date, keyword=None)[:20]:
            merged[row_item["id"]] = row_item
    else:
        for kw in keywords[:6]:
            rows = db.search_schedules_by_keyword(date=target_date, keyword=kw)
            for row_item in rows:
                merged[row_item["id"]] = row_item
            if len(merged) >= 20:
                break

    candidates = list(merged.values())[:20]
    return {
        "status": "success",
        "hint": {"target_date": target_date, "target_keyword": target_keyword, "keywords": keywords[:6]},
        "data": candidates[:20]
    }


@router.post("/requests/review")
def review_request(payload: ReviewRequest, admin=Depends(require_admin)):
    request_row = db.get_admin_request_by_id(payload.request_id)
    if not request_row:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다.")
    if request_row["status"] != "pending":
        raise HTTPException(status_code=400, detail="이미 처리된 요청입니다.")

    if payload.decision == "reject":
        db.update_admin_request_status(payload.request_id, "rejected")
        return {"status": "success", "message": "요청을 반려했습니다."}

    if payload.decision != "approve":
        raise HTTPException(status_code=400, detail="decision 값이 올바르지 않습니다.")

    request_type = request_row.get("request_type", "")
    applied = False

    # 요청에 schedule_data가 있으면 우선 사용, 없으면 DB payload_json에서 읽어 처리
    payload_data = payload.schedule_data
    if payload_data is None and request_row.get("payload_json"):
        try:
            parsed = json.loads(request_row["payload_json"])
            payload_data = parsed.get("schedule_data") if isinstance(parsed, dict) else None
            if payload.schedule_id is None and isinstance(parsed, dict):
                payload.schedule_id = parsed.get("schedule_id")
        except Exception:
            payload_data = None

    if request_type in ["update_request"] and payload.schedule_id and payload_data:
        applied = db.update_schedule_by_id(
            payload.schedule_id,
            payload_data,
            actor_user=admin["user_id"],
            actor_device=admin.get("device_name", "admin-device"),
        )
    elif request_type in ["delete_request"] and payload.schedule_id:
        applied = db.soft_delete_schedule_by_id(
            schedule_id=payload.schedule_id,
            deleted_by=admin["user_id"],
            delete_reason=payload.reason,
            actor_device=admin.get("device_name", "admin-device"),
        )
    elif request_type in ["other", "update_request", "delete_request", "unclassified"]:
        # 분류/상담성 요청은 승인 처리만 수행
        applied = True
    else:
        applied = True

    db.update_admin_request_status(payload.request_id, "approved" if applied else "failed")
    if not applied:
        raise HTTPException(status_code=400, detail="요청 적용에 실패했습니다. 데이터 확인이 필요합니다.")
    return {"status": "success", "message": "요청이 승인 처리되었습니다."}


@router.post("/field-staff")
def add_field_staff(payload: FieldStaffCreate, _admin=Depends(require_admin)):
    try:
        new_id = db.add_field_staff(payload.name.strip(), payload.sort_order)
        return {"status": "success", "id": new_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 등록된 이름입니다.")


@router.delete("/field-staff/{staff_id}")
def delete_field_staff(staff_id: int, _admin=Depends(require_admin)):
    if not db.delete_field_staff(staff_id):
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제되었습니다."}


@router.post("/export/daily")
def run_daily_export(payload: DailyExportRequest, _admin=Depends(require_admin)):
    target_date = payload.target_date or DailyExportService.yesterday_str()
    try:
        result = export_svc.export_date(target_date)
        return {"status": "success", "message": "일일 내보내기가 완료되었습니다.", "data": result}
    except Exception as e:
        db.create_export_job(target_date=target_date, status="failed", output_path="", message=str(e))
        raise HTTPException(status_code=500, detail=f"일일 내보내기 실패: {e}")
