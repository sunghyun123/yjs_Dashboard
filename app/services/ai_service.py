# app/services/ai_service.py
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


# 1. 일정 데이터 구조 (create, update 시 후보 데이터 작성용)
class ScheduleSchema(BaseModel):
    date: str = Field(description="YYYY-MM-DD 형식의 날짜")
    task: str = Field(description="주요 작업 명칭")
    person: str = Field(default="-", description="담당자 또는 작업자 이름")
    details: str = Field(default="", description="참여자, 장비, 특이사항 등 상세 내용")
    work_code: str = Field(default="", description="현장 내부 공사 코드")
    shift_type: Optional[Literal["주간", "야간"]] = Field(
        default=None,
        description="근무 구분(미지정 시 공사 카테고리는 주간으로 기본 처리)",
    )
    category: Optional[Literal["공사 일정", "일정"]] = Field(
        default=None,
        description="상황판 카테고리(공사 일정 또는 일정)",
    )


# 2. [V2 신규] 대화형 의도 분석 구조
class ActionSchema(BaseModel):
    intent: Literal["create", "delete", "update", "search", "incomplete"] = Field(
        description="사용자 발화의 핵심 의도"
    )
    target_date: Optional[str] = Field(
        default=None, description="명령에서 추출된 대상 날짜 (YYYY-MM-DD 형식). 특정할 수 없으면 null"
    )
    target_keyword: Optional[str] = Field(
        default=None, description="검색/수정/삭제 시 후보를 찾기 위한 장소나 작업명 키워드. 없으면 null"
    )
    schedule_data: Optional[ScheduleSchema] = Field(
        default=None, description="새로 생성(create)하거나 수정(update)할 때 필요한 구체적 일정 데이터"
    )
    reply_message: str = Field(
        description="사용자에게 채팅창으로 건넬 자연스럽고 친절한 한국어 응답 메시지 (예: '어떤 일정을 지울까요?', '아래 일정을 등록할까요?')"
    )


class GeminiService:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3-flash-preview"

    async def process_command(self, text: str, input_category: str = "공사") -> Optional[Dict[str, Any]]:
        # 시스템 프롬프트에 동적으로 현재 날짜 주입 (YYYY-MM-DD)
        current_date = datetime.now().strftime("%Y-%m-%d")

        normalized_input_category = "일정" if str(input_category or "").strip() == "일정" else "공사"

        system_instruction = f"""
        당신은 건설 현장 상황판의 스마트 AI 어시스턴트입니다. (오늘 날짜 기준: {current_date})
        사용자의 메시지를 분석하여 데이터베이스를 직접 조작하는 대신, '사용자의 의도'를 파악하고 DB 검색 조건이나 후보 데이터를 추출하세요.
        사용자가 선택한 입력 카테고리는 "{normalized_input_category}" 입니다.

        [카테고리/근무 기본 규칙]
        - 입력 카테고리가 "공사"이면 schedule_data.category는 "공사 일정"으로 작성하세요.
        - 입력 카테고리가 "일정"이면 schedule_data.category는 "일정"으로 작성하세요.
        - 공사 일정인데 사용자가 주간/야간을 명시하지 않으면 shift_type은 "주간"으로 작성하세요.
        - shift_type은 "주간" 또는 "야간"만 사용하세요. ("심야"는 사용 금지)

        [의도(intent) 분류 기준 및 지시사항]
        1. create (등록): 새로운 일정을 추가하려는 경우. 
           - schedule_data를 최대한 채워주세요. 
           - reply_message 예시: "다음 내용으로 일정을 등록할까요?"
        2. delete (삭제): 기존 일정을 지우려는 경우. 
           - target_date나 target_keyword(장소/작업명)를 추출하세요. (정확한 ID를 모르므로 검색할 조건만 뽑습니다.)
           - reply_message 예시: "삭제할 일정을 찾아봤어요. 아래 목록에서 선택해 주세요."
        3. update (수정): 기존 일정을 변경하려는 경우.
           - 변경 대상을 찾기 위해 target_date나 target_keyword를 추출하고, 새롭게 덮어쓸 내용은 schedule_data에 담아주세요.
           - reply_message 예시: "수정할 일정을 찾았습니다. 이렇게 내용을 바꿀까요?"
        4. search (조회): 단순히 일정을 보여달라고 하는 경우.
           - target_date나 target_keyword를 추출하세요.
           - reply_message 예시: "요청하신 일정 목록입니다."
        5. incomplete (정보 부족): 무언가 요청했으나 날짜, 작업명 등 핵심 정보가 너무 부족하여 도저히 검색이나 생성을 할 수 없는 경우.
           - reply_message를 통해 부족한 정보를 되물어보세요. 예: "언제, 어디서 하는 일정인지 장소나 날짜를 조금 더 자세히 알려주세요!"

        [중요] reply_message는 마치 메신저에서 대화하듯, 작업자에게 친근하고 명확한 존댓말로 작성해야 합니다.
        """

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ActionSchema,
                    temperature=0.0
                )
            )
            # JSON 응답을 딕셔너리로 변환하여 반환
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"AI 의도 분석 오류: {e}")
            return None