import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import google.generativeai as genai
from pydantic import BaseModel, Field

# from app.core.config import settings

# 1. 로거(Logger) 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# 2. Pydantic을 활용한 응답 스키마 정의 (제미나이가 이 구조를 무조건 따르게 강제함)
class ScheduleSchema(BaseModel):
    date: str = Field(description="작업 기준 날짜 (YYYY-MM-DD 형식). 파악 불가시 빈 문자열('') 입력")
    location: str = Field(description="현장 위치, 지명 또는 건물명. 파악 불가시 빈 문자열('') 입력")
    task: str = Field(description="수행한 작업 내용 요약 (명사형). 파악 불가시 빈 문자열('') 입력")
    person: str = Field(description="담당자, 수신자 (다수일 경우 쉼표로 구분). 파악 불가시 빈 문자열('') 입력")
    category: str = Field(description="작업완료, 업무요청, 이슈보고, 일정공유, 기타 중 택 1")

class GeminiService:
    def __init__(self, api_key: str):
        # API 키 초기화
        genai.configure(api_key=api_key)
        # 텍스트 분석에 빠르고 적합한 flash 모델 사용
        self.model_name = "gemini-3-flash-preview"
        logger.info("GeminiService initialized.")

    async def parse_field_report(self, text: str) -> Optional[Dict[str, Any]]:
        """
        현장 작업 텍스트를 입력받아 구조화된 JSON(Dict)으로 반환합니다.
        실패 시 서버 중단을 막고 None을 반환합니다.
        """
        if not text or not text.strip():
            logger.warning("빈 텍스트가 입력되었습니다.")
            return None

        # API 호출 시점의 현재 날짜를 동적으로 계산
        current_date = datetime.now().strftime("%Y-%m-%d")

        system_instruction = f"""
        당신은 건설/현장 작업 보고 텍스트를 분석하여 구조화된 데이터로 변환하는 전문 AI 어시스턴트입니다.

        [지침]
        1. "오늘", "내일" 등의 상대적 날짜는 [기준 날짜]를 바탕으로 계산하세요.
        2. 텍스트에서 유추할 수 없는 정보는 반드시 null 처리하세요.

        [기준 날짜]
        {current_date}
        """

        try:
            logger.info(f"Gemini API 호출 시작 (입력 텍스트: '{text[:20]}...')")

            # 동적인 시스템 프롬프트를 위해 호출할 때마다 모델 인스턴스화
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )

            # 비동기(async) 방식으로 제미나이 호출
            response = await model.generate_content_async(
                contents=text,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=ScheduleSchema,  # Pydantic 스키마 강제 주입
                    temperature=0.1  # 일관된 출력을 위해 온도를 낮춤
                )
            )

            # 반환된 텍스트(JSON 문자열)를 파이썬 딕셔너리로 변환
            parsed_data = json.loads(response.text)
            logger.info("Gemini API 파싱 성공.")
            return parsed_data

        # 1. JSON 변환 에러 처리 (제미나이가 JSON 형식을 어겼을 경우)
        except json.JSONDecodeError as e:
            logger.error(f"[JSON 파싱 에러] 응답 데이터가 유효한 JSON이 아닙니다: {e}")
            logger.error(f"원본 응답: {response.text}")
            return None

        # 2. Google API 관련 에러 (네트워크 문제, 할당량 초과 등)
        except genai.types.generation_types.StopCandidateException as e:
            logger.error(f"[Gemini API 에러] 모델이 예기치 않게 응답을 중단했습니다: {e}")
            return None

        # 3. 기타 예기치 못한 에러 (서버 다운 방지)
        except Exception as e:
            logger.error(f"[시스템 에러] 제미나이 파싱 중 알 수 없는 에러 발생: {str(e)}", exc_info=True)
            return None


# 테스트용 코드 (직접 실행해 볼 수 있도록)
if __name__ == "__main__":
    import asyncio

    # 여기에 실제 발급받은 API 키를 넣어 테스트해 보세요
    # 실제 환경에서는 settings.GEMINI_API_KEY 를 전달합니다
    API_KEY = ""


    async def run_test():
        ai_service = GeminiService(api_key=API_KEY)
        sample_text = "오늘 안양 현장 접지 끝남. 김대리님한테 전달 좀 해줘"
        result = await ai_service.parse_field_report(sample_text)

        print("\n--- 파싱 결과 ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))


    asyncio.run(run_test())