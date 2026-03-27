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
    input_category: Literal["schedule_create", "general_work", "memo", "other", "update_request", "delete_request"] = Field(
        default="schedule_create",
        description="사용자 선택 입력 카테고리"
    )
    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "오늘 안양 현장 접지 끝남. 김대리님한테 전달 좀"}}
    )


class ExecuteRequest(BaseModel):
    action: Literal["create", "update", "delete"] = Field(..., description="실행할 액션 타입")
    schedule_data: Optional[Dict[str, Any]] = Field(default=None, description="생성/수정 시 저장할 일정 데이터")
    schedule_id: Optional[int] = Field(default=None, description="삭제 시 필요한 일정 고유 ID")


class MemoCreateRequest(BaseModel):
    content: str = Field(..., description="메모 내용")
    target_date: Optional[str] = Field(default=None, description="YYYY-MM-DD, 없으면 오늘")
    memo_type: str = Field(default="일반", description="메모 유형")
    linked_schedule_id: Optional[int] = Field(default=None, description="연결된 일정 ID")
    visibility: str = Field(default="all", description="all 또는 private")


class WorkerStatusRequest(BaseModel):
    user_name: str = Field(..., description="상태 대상 사용자")
    status: Literal["사무실", "외출", "야간작업"] = Field(..., description="변경 상태")
    location: str = Field(default="", description="장소")
    until_time: str = Field(default="", description="외출 종료시각 ISO 문자열")
    note: str = Field(default="", description="메모")


class BoardTemplateActionRequest(BaseModel):
    action_type: Literal["register", "memo", "update_request", "delete_request"] = Field(
        ...,
        description="전자칠판 템플릿 액션 타입"
    )
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    location: str = Field(default="", description="현장 위치")
    task: str = Field(default="", description="작업 내용")
    person: str = Field(default="", description="담당자")
    details: str = Field(default="", description="상세 내용")
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


# 4. 엔드포인트 통합

@router.post("/chat", summary="[V2] 대화형 의도 분석 및 후보 검색")
async def chat_with_ai(request: ChatRequest, user_session=Depends(require_session)):
    """
    사용자의 자연어 명령을 AI가 분석하여 의도를 파악하고, 필요한 경우 DB에서 후보 데이터를 검색합니다.
    (이 단계에서는 실제 DB 변경이 일어나지 않습니다.)
    """
    logger.info(f"새로운 채팅 메시지 수신: {request.text}")

    # 카테고리 기반 즉시 관리자 큐 라우팅
    if request.input_category in ["other", "update_request", "delete_request"]:
        req_id = db.create_admin_request(
            request_type=request.input_category,
            source_category=request.input_category,
            request_text=request.text,
            summary=f"[{request.input_category}] 사용자 요청 접수",
            payload_json="",
            requested_by=user_session["user_id"],
        )
        return {
            "intent": "incomplete",
            "reply_message": f"요청이 관리자 검토 큐로 접수되었습니다. (요청번호: #{req_id})",
            "candidates": [],
            "schedule_data": None
        }

    if request.input_category == "memo":
        memo_id = db.create_memo(
            content=request.text,
            target_date=datetime.now().strftime("%Y-%m-%d"),
            memo_type="일반",
            linked_schedule_id=None,
            visibility="all",
            actor_user=user_session["user_id"],
            actor_device=user_session.get("device_name", "unknown-device"),
        )
        return {
            "intent": "incomplete",
            "reply_message": f"메모가 등록되었습니다. (메모번호: #{memo_id})",
            "candidates": [],
            "schedule_data": None
        }

    # 1. AI 의도 분석기 호출
    action_data = await ai_svc.process_command(request.text)

    if not action_data:
        raise HTTPException(status_code=400, detail="AI가 메시지를 분석하지 못했습니다.")

    intent = action_data.get('intent')
    reply_message = action_data.get('reply_message', "명령을 처리할 수 없습니다.")
    target_date = action_data.get('target_date')
    target_keyword = action_data.get('target_keyword')
    schedule_data = action_data.get('schedule_data')
    if request.input_category == "general_work" and isinstance(schedule_data, dict):
        # '일반 작업'은 기존 일정 등록 플로우를 사용하되 category를 강제한다.
        schedule_data["category"] = "일반 작업"

    logger.info(f"AI 판단 의도: {intent}")

    candidates = []

    try:
        if intent in ["update", "delete"]:
            req_id = db.create_admin_request(
                request_type=f"{intent}_request",
                source_category=request.input_category,
                request_text=request.text,
                summary=f"AI가 {intent} 요청으로 분류",
                payload_json=json.dumps(action_data, ensure_ascii=False),
                requested_by=user_session["user_id"],
            )
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

        return {
            "intent": intent,
            "reply_message": reply_message,
            "candidates": candidates,
            "schedule_data": schedule_data
        }

    except Exception as e:
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


@router.get("/today", summary="상황판용 오늘자 일정 조회")
def get_todays_schedules(date: Optional[str] = None, _user_session=Depends(require_session)):
    """
    (기존 유지) 대시보드 화면을 그릴 때 전체 일정을 가져오는 엔드포인트
    """
    try:
        if date:
            schedules = db.search_schedules_by_keyword(date=date, keyword=None)
        else:
            schedules = db.get_schedules_for_window(base_date=None, past_days=3, future_days=7)
        return {"message": "조회 성공", "count": len(schedules), "data": schedules}
    except Exception as e:
        logger.error(f"일정 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")


@router.post("/memos", summary="기타 메모 등록")
def create_memo(request: MemoCreateRequest, user_session=Depends(require_session)):
    target_date = request.target_date or datetime.now().strftime("%Y-%m-%d")
    memo_id = db.create_memo(
        content=request.content,
        target_date=target_date,
        memo_type=request.memo_type,
        linked_schedule_id=request.linked_schedule_id,
        visibility=request.visibility,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    return {"status": "success", "message": "메모가 등록되었습니다.", "memo_id": memo_id}


@router.delete("/memos/{memo_id}", summary="메모 삭제")
def delete_memo(memo_id: int, user_session=Depends(require_session)):
    success = db.soft_delete_memo(
        memo_id=memo_id,
        actor_user=user_session["user_id"],
        actor_device=user_session.get("device_name", "unknown-device"),
    )
    if not success:
        raise HTTPException(status_code=404, detail="삭제할 메모를 찾을 수 없습니다.")
    return {"status": "success", "message": "메모가 삭제되었습니다."}


@router.get("/memos", summary="메모 조회")
def list_memos(date: Optional[str] = None, _user_session=Depends(require_session)):
    return {"status": "success", "data": db.list_memos(target_date=date)}


@router.post("/worker-status", summary="외출/야간/사무실 상태 변경")
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


@router.get("/worker-status", summary="외출/야간/사무실 상태 조회")
def get_worker_status(_user_session=Depends(require_session)):
    return {"status": "success", "data": db.list_worker_status()}


@router.delete("/worker-status/{user_name}", summary="외출/야간/사무실 상태 삭제")
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
                "location": request.location,
                "task": request.task,
                "person": request.person or "",
                "details": request.details,
                "tags": [],
                "category": request.category or "공사 일정",
            },
            actor_user=actor_user,
            actor_device=actor_device,
        )
        return {"status": "success", "message": result_msg}

    if request.action_type == "memo":
        memo_id = db.create_memo(
            content=request.task or request.details or request.request_note,
            target_date=target_date,
            memo_type="일반",
            linked_schedule_id=None,
            visibility="all",
            actor_user=actor_user,
            actor_device=actor_device,
        )
        return {"status": "success", "message": f"전자칠판 메모 등록 완료 (#{memo_id})"}

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
                "location": request.location,
                "task": request.task,
                "person": request.person or "",
                "details": request.details,
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