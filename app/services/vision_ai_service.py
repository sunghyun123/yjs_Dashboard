import json
import logging
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class AnalysisResult(BaseModel):
    doc_type: Literal["작업일지", "영수증", "자재명세서", "확인필요_미분류"] = Field(description="문서 종류")
    project_name: str = Field(default="미파악공사", description="공사명")
    project_code: str = Field(default="000-000", description="공사코드")
    work_date: str = Field(default="0000-00-00", description="작업일자")
    is_night: bool = Field(default=False, description="야간 작업 여부")

    work_time_text: str = Field(default="", description="공사시간 원문 (예: 08:30 - 17:00)")
    regular_count: float = Field(default=0)
    daily_count: float = Field(default=0)
    signalman_count: float = Field(default=0)
    excavator_6w: float = Field(default=0)
    excavator_3w: float = Field(default=0)
    dump_15t: float = Field(default=0)
    crane_count: float = Field(default=0)
    connection_count: float = Field(default=0, description="오륜전기접속(접속) 수량")


class VisionService:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3-flash-preview"

    async def analyze_document(self, image_bytes: bytes, mime_type: str) -> Optional[Dict[str, Any]]:
        prompt = """
이 이미지는 시공팀 작업일지다. 문서 종류를 분류하고 ERP 입력용 구조화 데이터를 JSON으로 응답하라.

반드시 다음 규칙으로 계산한다.
1) 공사명: "공사명" 필드의 텍스트를 project_name 으로 추출.
2) 작업일자: "작업일자"를 YYYY-MM-DD로 정규화하여 work_date에 저장.
3) 공사시간 원문은 work_time_text에 보관하고, 주야간은 다음으로 판정:
   - 시작 시간이 18:00 이상이거나 "야간" 문구가 있으면 is_night=true
   - 그 외는 is_night=false
4) "투입인원 및 장비 현황" 표에서 동그라미(체크) 수를 기준으로 계산:
   - 상용직(regular_count) = [임재홍, 이한열, 최정우, 김성훈, 김종인, 김국진, 박상정, 김기태, 한동근]의 동그라미 개수 + 1
   - 일용직(daily_count) = [일용인력, 변산인력]의 동그라미 개수 + 1
   - 모범신호수(signalman_count) = [모범신호수, 전문신호수] 동그라미 개수 합 + 1
   - 접속(connection_count) = [오륜전기접속] 동그라미 개수 + 1
5) 장비 수량은 표의 장비 항목 숫자를 그대로 추출:
   - 굴착기 6W -> excavator_6w
   - 굴착기 3W -> excavator_3w
   - 덤프트럭 15T -> dump_15t
   - 크레인 -> crane_count

주의:
- 값이 불명확하면 0 사용.
- 숫자는 float 허용(예: 0.5).
- project_code는 문서에 명확히 없으면 "000-000".
- doc_type은 작업일지면 반드시 "작업일지".
"""
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AnalysisResult,
                    temperature=0.0
                )
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"비전 분석 오류: {e}")
            return None