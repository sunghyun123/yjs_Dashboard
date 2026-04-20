# app/api/schedules.py
import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, Literal
import logging
from datetime import datetime

from app.services.ai_service import GeminiService
from app.db.db_manager import DBManager
from app.core.config import settings
from app.core.auth import require_session

logger = logging.getLogger(__name__)

# 1. 라우터 생성
router = APIRouter(prefix="/api/schedules", tags=["Schedules"])

# 2. 의존성 객체 초기화
ai_svc = GeminiService(api_key=settings.GEMINI_API_KEY)
db = DBManager(db_path=settings.sqlite_db_path)


# 3. Request 모델
class ChatRequest(BaseModel):
    text: str = Field(..., description="사용자가 채팅창에 입력한 자연어 메시지")
    input_category: Literal["공사", "일정", "schedule_create", "general_work", "other", "update_request", "delete_request"] = Field(
        default="공사",
        description="사용자 선택 입력 카테고리"
    )
    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "오늘 안양 현장 접지 끝남. 김대리님한테 전달 좀"}}
    )


class ExecuteRequest(BaseModel):
    action: Literal["create", "update", "delete"] = Field(..., description="실행할 액션 타입")
    schedule_data: Optional[Dict[str, Any]] = Field(default=None, description="생성/수정 시 저장할 일정 데이터")
    schedule_id: Optional[int] = Field(default=None, description="삭제 시 필요한 일정 고유 ID")


class WorkerStatusRequest(BaseModel):
    user_name: str = Field(..., description="상태 대상 사용자")
    status: Literal["사무실", "외출", "야간작업", "휴가"] = Field(..., description="변경 상태")
    location: str = Field(default="", description="장소")
    until_time: str = Field(default="", description="외출 종료시각 ISO 문자열")
    note: str = Field(default="", description="메모")


class BoardTemplateActionRequest(BaseModel):
    action_type: Literal["register", "update_request", "delete_request"] = Field(
        ...,
        description="전자칠판 템플릿 액션 타입"
    )
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    task: str = Field(default="", description="작업 내용")
    person: str = Field(default="", description="담당자")
    details: str = Field(default="", description="상세 내용")
    work_code: str = Field(default="", description="공사 코드")
    shift_type: Literal["", "주간", "야간", "심야"] = Field(
        default="",
        description="근무 구분(API·레거시 호환 입력; 저장 계층에서 심야는 야간으로 정규화)",
    )
    category: str = Field(default="공사 일정", description="카테고리")
    request_note: str = Field(default="", description="수정/삭제 요청 시 관리자 메모")
    schedule_id: Optional[int] = Field(default=None, description="수정/삭제 대상 일정 ID")


class DirectScheduleUpdateRequest(BaseModel):
    schedule_id: int = Field(..., description="수정 대상 일정 ID")
    schedule_data: Dict[str, Any] = Field(..., description="수정 데이터")
    reason: str = Field(default="", description="수정 사유")


class DirectScheduleDeleteRequest(BaseModel):
    schedule_id: int = Field(..., description="삭제 대상 일정 ID")
    reason: str = Field(default="", description="삭제 사유")


class ReorderItem(BaseModel):
    schedule_id: int = Field(..., description="일정 ID")
    date: str = Field(..., description="이동 대상 날짜 (YYYY-MM-DD)")
    display_order: int = Field(..., description="표시 순서")


class ReorderBatchRequest(BaseModel):
    items: list[ReorderItem] = Field(default_factory=list, description="드래그 결과 목록")


class ImportConstructionPlanRequest(BaseModel):
    date: str = Field(..., description="저장할 작업일 YYYY-MM-DD")
    rows: list[Dict[str, Any]] = Field(default_factory=list, description="공사일정계획서 추출 검토 행")


def _normalize_work_code_for_plan(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    for open_b, close_b in (("(", ")"), ("<", ">"), ("（", "）"), ("[", "]")):
        if len(s) > 2 and s.startswith(open_b) and s.endswith(close_b):
            s = s[1:-1].strip()
            break
    return s.strip()


def _shift_hint_from_plan_text(*parts: str) -> str:
    blob = " ".join((p or "") for p in parts)
    if "야간" in blob or "심야" in blob:
        return "야간"
    if "주간" in blob:
        return "주간"
    return ""


def _plan_task_overlap(new_task: str, existing_task: str) -> bool:
    a = "".join((new_task or "").lower().split())
    b = "".join((existing_task or "").lower().split())
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    if len(a) >= 10 and len(b) >= 10 and a[:14] == b[:14]:
        return True
    return False


def _normalize_chat_input_category(raw: str) -> str:
    val = str(raw or "").strip()
    if val in ("공사", "schedule_create"):
        return "공사"
    if val in ("일정", "general_work"):
        return "일정"
    if val in ("other", "update_request", "delete_request"):
        return val
    return "공사"


def _apply_chat_category_policy(input_category: str, schedule_data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(schedule_data or {})
    normalized_input = _normalize_chat_input_category(input_category)
    if normalized_input == "공사":
        data["category"] = "공사 일정"
        # 공사는 주간/야간 미지정 시 주간 기본값을 사용한다.
        if str(data.get("shift_type") or "").strip() not in ("주간", "야간"):
            data["shift_type"] = "주간"
    elif normalized_input == "일정":
        data["category"] = "일정"
        if str(data.get("shift_type") or "").strip() not in ("주간", "야간"):
            data["shift_type"] = ""
    return data


# 4. 엔드포인트 통합

@router.post("/chat", summary="[V2] 대화형 의도 분석 및 후보 검색")
async def chat_with_ai(request: ChatRequest, user_session=Depends(require_session)):
    """
    사용자의 자연어 명령을 AI가 분석하여 의도를 파악하고, 필요한 경우 DB에서 후보 데이터를 검색합니다.
    (이 단계에서는 실제 DB 변경이 일어나지 않습니다.)
    """
    logger.info(f"새로운 채팅 메시지 수신: {request.text}")
    response_intent = "incomplete"
    response_status = "success"

    def record_chat_event() -> None:
        db.log_chat_event(
            user_id=user_session.get("user_id", ""),
            input_category=request.input_category,
            message_text=request.text,
            intent=response_intent,
            response_status=response_status,
        )

    normalized_input_category = _normalize_chat_input_category(request.input_category)

    # 카테고리 기반 즉시 관리자 큐 라우팅
    if normalized_input_category in ["other", "update_request", "delete_request"]:
        req_id = db.create_admin_request(
            request_type=normalized_input_category,
            source_category=normalized_input_category,
            request_text=request.text,
            summary=f"[{normalized_input_category}] 사용자 요청 접수",
            payload_json="",
            requested_by=user_session["user_id"],
        )
        response_intent = "incomplete"
        record_chat_event()
        return {
            "intent": "incomplete",
            "reply_message": f"요청이 관리자 검토 큐로 접수되었습니다. (요청번호: #{req_id})",
            "candidates": [],
            "schedule_data": None
        }

    # 1. AI 의도 분석기 호출
    action_data = await ai_svc.process_command(request.text, normalized_input_category)

    if not action_data:
        response_status = "error"
        response_intent = "ai_parse_failed"
        record_chat_event()
        raise HTTPException(status_code=400, detail="AI가 메시지를 분석하지 못했습니다.")

    intent = action_data.get('intent')
    reply_message = action_data.get('reply_message', "명령을 처리할 수 없습니다.")
    target_date = action_data.get('target_date')
    target_keyword = action_data.get('target_keyword')
    schedule_data = action_data.get('schedule_data')
    if isinstance(schedule_data, dict):
        schedule_data = _apply_chat_category_policy(normalized_input_category, schedule_data)

    logger.info(f"AI 판단 의도: {intent}")

    candidates = []

    try:
        if intent in ["update", "delete"]:
            req_id = db.create_admin_request(
                request_type=f"{intent}_request",
                source_category=normalized_input_category,
                request_text=request.text,
                summary=f"AI가 {intent} 요청으로 분류",
                payload_json=json.dumps(action_data, ensure_ascii=False),
                requested_by=user_session["user_id"],
            )
            response_intent = "incomplete"
            record_chat_event()
            return {
                "intent": "incomplete",
                "reply_message": f"요청이 관리자 승인 큐로 접수되었습니다. (요청번호: #{req_id})",
                "candidates": [],
                "schedule_data": None
            }

        # 2. 의도에 따른 DB 검색 로직 (조회, 수정, 삭제의 경우 후보 찾기)
        if intent in ["search"]:
            candidates = db.search_schedules_by_keyword(date=target_date, keyword=target_keyword)

            if not candidates:
                reply_message = "말씀하신 조건의 조회 결과가 없습니다. 날짜나 장소를 다시 알려주세요."
                intent = "incomplete"

        response_intent = str(intent or "incomplete")
        record_chat_event()
        return {
            "intent": intent,
            "reply_message": reply_message,
            "candidates": candidates,
            "schedule_data": schedule_data
        }

    except Exception as e:
        response_status = "error"
        response_intent = str(intent or "server_error")
        try:
            record_chat_event()
        except Exception:
            pass
        logger.error(f"채팅 의도 분석 중 에러 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")


@router.post("/execute", summary="[V2] 사용자 확인 후 DB 실제 반영")
async def execute_action(request: ExecuteRequest, user_session=Depends(require_session)):
    """
    채팅창에서 사용자가 AI가 제시한 후보를 보고 [등록], [수정], [삭제] 등의 버튼을 눌렀을 때 호출됩니다.
    실제로 DB를 변경합니다.
    """
    action = request.action
    logger.info(f"사용자 최종 승인 액션 실행: {action}")

    try:
        # 1. 생성(create) 동작
        if action == "create":
            if not request.schedule_data:
                raise HTTPException(status_code=400, detail="일정 데이터가 누락되었습니다.")

            result_msg = db.upsert_schedule(
                request.schedule_data,
                actor_user=user_session["user_id"],
                actor_device=user_session.get("device_name", "unknown-device"),
            )
            return {"message": result_msg, "status": "success"}

        # 2. 수정/삭제는 관리자 큐로 접수
        elif action in ["update", "delete"]:
            req_id = db.create_admin_request(
                request_type=f"{action}_request",
                source_category=f"{action}_execute",
                request_text="사용자 실행 버튼 요청",
                summary=f"사용자 {action} 실행 요청",
                payload_json=json.dumps({
                    "schedule_id": request.schedule_id,
                    "schedule_data": request.schedule_data
                }, ensure_ascii=False),
                requested_by=user_session["user_id"],
            )
            return {"message": f"관리자 승인 요청으로 접수되었습니다. (요청번호: #{req_id})", "status": "success"}

        else:
            raise HTTPException(status_code=400, detail="알 수 없는 액션입니다.")

    except Exception as e:
        logger.error(f"DB 실행 실패 ({action}): {e}")
        if isinstance(e, ValueError):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/field-staff", summary="현장직 이름 목록 (작업 인원 선택)")
def list_field_staff(_user_session=Depends(require_session)):
    return {"status": "success", "data": db.list_field_staff()}


@router.get("/outing-staff", summary="외출/행선표 고정 인원 목록")
def list_outing_staff(_user_session=Depends(require_session)):
    return {"status": "success", "data": db.list_outing_staff()}


@router.get("/frequent-sites", summary="홈 바로가기(자주 가는 사이트) 목록")
def list_frequent_sites(_user_session=Depends(require_session)):
    return {"status": "success", "data": db.list_frequent_sites()}


@router.get("/today", summary="상황판용 오늘자 일정 조회")
def get_todays_schedules(
    date: Optional[str] = None,
    range_start: Optional[str] = None,
    range_end: Optional[str] = None,
    _user_session=Depends(require_session),
):
    """
    (기존 유지) 대시보드 화면을 그릴 때 전체 일정을 가져오는 엔드포인트
    """
    try:
        if range_start and range_end:
            start_dt = datetime.strptime(range_start, "%Y-%m-%d")
            end_dt = datetime.strptime(range_end, "%Y-%m-%d")
            if start_dt > end_dt:
                raise HTTPException(status_code=400, detail="range_start는 range_end보다 이전 날짜여야 합니다.")
            schedules = db.search_schedules_by_date_range(range_start, range_end)
        elif date:
            schedules = db.search_schedules_by_keyword(date=date, keyword=None)
        else:
            schedules = db.get_schedules_for_window(base_date=None, past_days=3, future_days=7)
        return {"message": "조회 성공", "count": len(schedules), "data": schedules}
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD 이어야 합니다.")
    except Exception as e:
        logger.error(f"일정 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")


@router.post("/worker-status", summary="외출/야간/휴가/사무실 상태 변경")
def set_worker_status(request: WorkerStatusRequest, user_session=Depends(require_session)):
    db.upsert_worker_status(
        user_name=request.user_name,
        status=request.status,
        location=request.location,
        until_time=request.until_time,
        note=request.note,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    return {"status": "success", "message": "상태가 변경되었습니다."}


@router.get("/worker-status", summary="외출/야간/휴가/사무실 상태 조회")
def get_worker_status(_user_session=Depends(require_session)):
    return {"status": "success", "data": db.list_worker_status()}


@router.delete("/worker-status/{user_name}", summary="외출/야간/휴가/사무실 상태 삭제")
def delete_worker_status(user_name: str, _user_session=Depends(require_session)):
    if not user_name.strip():
        raise HTTPException(status_code=400, detail="삭제할 사용자명이 필요합니다.")
    deleted = db.delete_worker_status(user_name.strip())
    if not deleted:
        raise HTTPException(status_code=404, detail="삭제할 상태 항목을 찾을 수 없습니다.")
    return {"status": "success", "message": "상태 항목이 삭제되었습니다."}


@router.post("/board/template-action", summary="전자칠판 템플릿 액션 처리")
def board_template_action(request: BoardTemplateActionRequest, _user_session=Depends(require_session)):
    target_date = request.date or datetime.now().strftime("%Y-%m-%d")
    actor_user = "전자칠판"
    actor_device = "lg-create-board"

    if request.action_type == "register":
        result_msg = db.upsert_schedule(
            {
                "date": target_date,
                "location": "",
                "task": request.task,
                "person": request.person or "",
                "details": request.details,
                "work_code": request.work_code or "",
                "shift_type": request.shift_type or "",
                "tags": [],
                "category": request.category or "공사 일정",
            },
            actor_user=actor_user,
            actor_device=actor_device,
        )
        return {"status": "success", "message": result_msg}

    req_type = "update_request" if request.action_type == "update_request" else "delete_request"
    req_id = db.create_admin_request(
        request_type=req_type,
        source_category="board_template",
        request_text=request.request_note or request.task or request.details or "전자칠판 요청",
        summary=f"전자칠판 {req_type} 접수",
        payload_json=json.dumps({
            "schedule_id": request.schedule_id,
            "schedule_data": {
                "date": target_date,
                "location": "",
                "task": request.task,
                "person": request.person or "",
                "details": request.details,
                "work_code": request.work_code or "",
                "shift_type": request.shift_type or "",
                "tags": [],
                "category": request.category or "공사 일정",
            }
        }, ensure_ascii=False),
        requested_by="전자칠판",
    )
    return {"status": "success", "message": f"관리자 요청 접수 완료 (#{req_id})"}


@router.post("/direct-update", summary="현황판/전자칠판 즉시 수정")
def direct_update_schedule(request: DirectScheduleUpdateRequest, user_session=Depends(require_session)):
    before = db.get_schedule_by_id(request.schedule_id)
    if not before or before.get("deleted_at"):
        raise HTTPException(status_code=404, detail="수정 대상 일정을 찾을 수 없습니다.")

    updated = db.update_schedule_by_id(
        request.schedule_id,
        request.schedule_data,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    if not updated:
        raise HTTPException(status_code=400, detail="일정 수정에 실패했습니다.")

    after = db.get_schedule_by_id(request.schedule_id)
    if str(before.get("source_kind") or "") == "photo_plan" and not int(before.get("photo_plan_acknowledged") or 0):
        db.acknowledge_photo_plan_schedule(
            request.schedule_id,
            actor_user=user_session["user_id"],
            actor_device=user_session.get("device_name", "unknown-device"),
        )
        after = db.get_schedule_by_id(request.schedule_id)
    db.create_audit_event(
        entity_type="field_schedules",
        entity_id=request.schedule_id,
        action="direct_update",
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=request.reason,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    return {"status": "success", "message": "일정이 즉시 수정되었습니다."}


@router.post("/direct-delete", summary="현황판/전자칠판 즉시 삭제")
def direct_delete_schedule(request: DirectScheduleDeleteRequest, user_session=Depends(require_session)):
    before = db.get_schedule_by_id(request.schedule_id)
    if not before or before.get("deleted_at"):
        raise HTTPException(status_code=404, detail="삭제 대상 일정을 찾을 수 없습니다.")

    deleted = db.soft_delete_schedule_by_id(
        schedule_id=request.schedule_id,
        deleted_by=user_session["user_id"],
        delete_reason=request.reason,
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    if not deleted:
        raise HTTPException(status_code=400, detail="일정 삭제에 실패했습니다.")

    after = db.get_schedule_by_id(request.schedule_id)
    db.create_audit_event(
        entity_type="field_schedules",
        entity_id=request.schedule_id,
        action="direct_delete",
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=request.reason,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    return {"status": "success", "message": "일정이 즉시 삭제되었습니다."}


@router.post("/reorder-batch", summary="현황판 드래그 순서 일괄 저장")
def reorder_batch(request: ReorderBatchRequest, user_session=Depends(require_session)):
    payload_items = [
        {"schedule_id": item.schedule_id, "date": item.date, "display_order": item.display_order}
        for item in request.items
    ]
    applied_count = db.apply_schedule_reorder(
        items=payload_items,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    return {"status": "success", "message": "정렬이 저장되었습니다.", "applied_count": applied_count}


@router.post("/import-construction-plan", summary="공사일정계획서 추출 행을 상황판에 반영")
def import_construction_plan(request: ImportConstructionPlanRequest, user_session=Depends(require_session)):
    try:
        target_date = datetime.strptime(request.date.strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜는 YYYY-MM-DD 형식이어야 합니다.")

    existing = db.search_schedules_by_keyword(date=target_date, keyword=None)
    inserted_ids: list[int] = []
    overlap_warnings: list[Dict[str, Any]] = []

    for raw in request.rows:
        if not isinstance(raw, dict):
            continue
        task_title = str(raw.get("task", "")).strip()
        if not task_title:
            continue
        team = str(raw.get("team", "")).strip()
        display_task = task_title
        workers = str(raw.get("workers", "")).strip()
        detail_lines: list[str] = []
        if team:
            detail_lines.append(f"[팀] {team}")
        detail_lines.extend(
            [
                str(raw.get("shift_note", "")).strip(),
                str(raw.get("details", "")).strip(),
                str(raw.get("equipment", "")).strip(),
            ]
        )
        details_blob = "\n\n".join([p for p in detail_lines if p])
        wc = _normalize_work_code_for_plan(str(raw.get("work_code", "")).strip())
        shift_guess = _shift_hint_from_plan_text(
            raw.get("shift_note", ""),
            raw.get("details", ""),
            display_task,
        )
        shift_type = db._extract_shift_type(
            {"shift_type": shift_guess, "task": display_task, "details": details_blob}
        )

        sim_ids: list[int] = []
        for ex in existing:
            sk = str(ex.get("source_kind") or "manual").strip() or "manual"
            if sk == "photo_plan":
                continue
            et = str(ex.get("task") or "")
            if _plan_task_overlap(display_task, et) or _plan_task_overlap(task_title, et):
                sim_ids.append(int(ex["id"]))
        if sim_ids:
            overlap_warnings.append({"task": display_task, "similar_schedule_ids": sim_ids})

        new_id = db.insert_schedule_row(
            {
                "date": target_date,
                "task": display_task,
                "person": workers if workers else "-",
                "details": details_blob,
                "work_code": wc,
                "shift_type": shift_type,
                "tags": "",
                "category": "공사 일정",
                "source_kind": "photo_plan",
                "source_photo_upload_id": None,
            },
            actor_user=user_session["user_id"],
            actor_device=user_session.get("device_name", "unknown-device"),
        )
        inserted_ids.append(new_id)
        existing.append({"id": new_id, "task": display_task, "source_kind": "photo_plan"})

    return {
        "status": "success",
        "message": f"{len(inserted_ids)}건을 상황판에 등록했습니다.",
        "inserted_ids": inserted_ids,
        "overlap_warnings": overlap_warnings,
        "count": len(inserted_ids),
    }


class AcknowledgePhotoPlanRequest(BaseModel):
    schedule_id: int = Field(..., description="일정 ID")


@router.post("/acknowledge-photo-plan", summary="사진 추출 일정 검토 완료(자동추출 배지 숨김)")
def acknowledge_photo_plan(request: AcknowledgePhotoPlanRequest, user_session=Depends(require_session)):
    ok = db.acknowledge_photo_plan_schedule(
        request.schedule_id,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="대상 일정이 없거나 사진 추출 일정이 아닙니다.")
    return {"status": "success", "message": "검토 완료로 표시했습니다."}