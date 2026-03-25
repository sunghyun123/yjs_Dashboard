import json
import logging
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class AnalysisResult(BaseModel):
    # model_config 부분을 삭제했습니다.
    doc_type: Literal["작업일지", "영수증", "자재명세서", "확인필요_미분류"] = Field(description="문서 종류")
    project_name: str = Field(default="미파악공사", description="공사명")
    project_code: str = Field(default="000-000", description="공사코드")
    work_date: str = Field(default="0000-00-00", description="작업일자")
    is_night: bool = Field(default=False, description="야간 작업 여부")

    regular_count: int = Field(default=0)
    daily_count: int = Field(default=0)
    signalman_count: int = Field(default=0)
    excavator_6w: int = Field(default=0)
    excavator_3w: int = Field(default=0)
    dump_15t: int = Field(default=0)
    crane_count: int = Field(default=0)


class VisionService:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3-flash-preview"

    async def analyze_document(self, image_bytes: bytes, mime_type: str) -> Optional[Dict[str, Any]]:
        prompt = "이 이미지를 분석하여 문서 종류를 분류하고, ERP 입력에 필요한 숫자 데이터를 추출해 JSON으로 응답하세요."
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