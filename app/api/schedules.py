# app/api/schedules.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
import logging

from app.services.ai_service import GeminiService
from app.db.db_manager import DBManager
from app.core.config import settings

logger = logging.getLogger(__name__)

# 1. 라우터 생성
router = APIRouter(prefix="/api/schedules", tags=["Schedules"])

# 2. 의존성 객체 초기화
ai_svc = GeminiService(api_key=settings.GEMINI_API_KEY)
db = DBManager(db_path="schedule.db")


# 3. Request 모델
class ChatRequest(BaseModel):
    text: str = Field(..., description="사용자가 채팅창에 입력한 자연어 메시지")

    class Config:
        json_schema_extra = {
            "example": {"text": "오늘 안양 현장 접지 끝남. 김대리님한테 전달 좀"}
        }


class ExecuteRequest(BaseModel):
    action: Literal["create", "update", "delete"] = Field(..., description="실행할 액션 타입")
    schedule_data: Optional[Dict[str, Any]] = Field(default=None, description="생성/수정 시 저장할 일정 데이터")
    schedule_id: Optional[int] = Field(default=None, description="삭제 시 필요한 일정 고유 ID")


# 4. 엔드포인트 통합

@router.post("/chat", summary="[V2] 대화형 의도 분석 및 후보 검색")
async def chat_with_ai(request: ChatRequest):
    """
    사용자의 자연어 명령을 AI가 분석하여 의도를 파악하고, 필요한 경우 DB에서 후보 데이터를 검색합니다.
    (이 단계에서는 실제 DB 변경이 일어나지 않습니다.)
    """
    logger.info(f"새로운 채팅 메시지 수신: {request.text}")

    # 1. AI 의도 분석기 호출
    action_data = await ai_svc.process_command(request.text)

    if not action_data:
        raise HTTPException(status_code=400, detail="AI가 메시지를 분석하지 못했습니다.")

    intent = action_data.get('intent')
    reply_message = action_data.get('reply_message', "명령을 처리할 수 없습니다.")
    target_date = action_data.get('target_date')
    target_keyword = action_data.get('target_keyword')
    schedule_data = action_data.get('schedule_data')

    logger.info(f"AI 판단 의도: {intent}")

    candidates = []

    try:
        # 2. 의도에 따른 DB 검색 로직 (조회, 수정, 삭제의 경우 후보 찾기)
        if intent in ["delete", "update", "search"]:
            candidates = db.search_schedules_by_keyword(date=target_date, keyword=target_keyword)

            # 검색 결과가 없을 때 사용자에게 더 친절하게 안내하도록 응답 메시지 조정
            if not candidates and intent in ["delete", "update"]:
                reply_message = "말씀하신 조건에 맞는 일정을 찾지 못했어요. 날짜나 장소를 다시 한 번 확인해 주시겠어요?"
                intent = "incomplete"  # 데이터가 없으므로 불완전 상태로 전환

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
async def execute_action(request: ExecuteRequest):
    """
    채팅창에서 사용자가 AI가 제시한 후보를 보고 [등록], [수정], [삭제] 등의 버튼을 눌렀을 때 호출됩니다.
    실제로 DB를 변경합니다.
    """
    action = request.action
    logger.info(f"사용자 최종 승인 액션 실행: {action}")

    try:
        # 1. 생성(create) 및 수정(update) 동작
        if action in ["create", "update"]:
            if not request.schedule_data:
                raise HTTPException(status_code=400, detail="일정 데이터가 누락되었습니다.")

            result_msg = db.upsert_schedule(request.schedule_data)
            return {"message": result_msg, "status": "success"}

        # 2. 삭제(delete) 동작
        elif action == "delete":
            if not request.schedule_id:
                raise HTTPException(status_code=400, detail="삭제할 일정 ID가 누락되었습니다.")

            # 새롭게 만든 ID 기반 삭제 메서드 사용
            success = db.delete_schedule_by_id(request.schedule_id)

            if success:
                return {"message": f"🗑️ 일정이 정상적으로 삭제되었습니다.", "status": "success"}
            else:
                return {"message": f"⚠️ 데이터를 찾을 수 없어 삭제하지 못했습니다.", "status": "error"}

        else:
            raise HTTPException(status_code=400, detail="알 수 없는 액션입니다.")

    except Exception as e:
        logger.error(f"DB 실행 실패 ({action}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today", summary="상황판용 오늘자 일정 조회")
def get_todays_schedules(date: Optional[str] = None):
    """
    (기존 유지) 대시보드 화면을 그릴 때 전체 일정을 가져오는 엔드포인트
    """
    try:
        schedules = db.get_all_schedules_desc(target_date=date)
        return {"message": "조회 성공", "count": len(schedules), "data": schedules}
    except Exception as e:
        logger.error(f"일정 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")