from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# 앞서 작성한 모듈들을 불러옵니다 (실제 폴더 구조에 맞게 import)
from app.services.ai_service import GeminiService
from app.db.db_manager import DBManager

from app.core.config import settings # 환경변수 사용 시

# 로거 설정
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 1. FastAPI 앱 인스턴스 생성
app = FastAPI(
    title="현장 일정 자동화 API",
    description="현장 작업자의 비정형 텍스트를 AI로 분석하여 DB에 저장하고 제공합니다.",
    version="1.0.0"
)
# CORS 허가증 설정 (프론트엔드 HTML 파일이 API에 접근할 수 있게 해줌)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 지금은 테스트용이니 모든 접근을 허용합니다!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 전역 의존성 객체 초기화 (서버가 켜질 때 한 번만 실행됨)
ai_svc = GeminiService(api_key=settings.GEMINI_API_KEY)
db = DBManager(db_path="schedule.db")


# 3. 클라이언트 요청을 검증할 Pydantic 모델 (POST 요청의 Body)
class ReportRequest(BaseModel):
    text: str

    class Config:
        json_schema_extra = {
            "example": {
                "text": "오늘 안양 현장 접지 끝남. 김대리한테 전달 좀"
            }
        }


# --- API 엔드포인트 ---

@app.post("/api/schedules", summary="현장 보고 텍스트 분석 및 저장")
async def create_schedule(request: ReportRequest):
    """
    현장 직원이 보낸 비정형 텍스트를 받아 AI로 파싱한 뒤 데이터베이스에 저장합니다.
    """
    logger.info(f"새로운 현장 보고 수신: {request.text}")

    # 1. AI 서비스 호출 (텍스트 -> JSON 파싱)
    parsed_data = await ai_svc.parse_field_report(request.text)

    # 파싱 실패 시 클라이언트에게 명확한 에러 반환
    if not parsed_data:
        raise HTTPException(
            status_code=400,
            detail="AI가 텍스트를 분석하지 못했습니다. 내용을 조금 더 명확하게 작성해 주세요."
        )

    # 2. DB 저장
    try:
        inserted_id = db.insert_schedule(parsed_data)

        # 3. 성공 응답 반환
        return {
            "message": "일정이 성공적으로 등록되었습니다.",
            "id": inserted_id,
            "data": parsed_data
        }

    except Exception as e:
        logger.error(f"DB 저장 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail="데이터를 저장하는 중 서버 내부 오류가 발생했습니다."
        )


@app.get("/api/schedules/today", summary="상황판용 오늘자 일정 조회")
def get_todays_schedules(date: Optional[str] = None):
    """
    상황판에 띄울 일정 목록을 가져옵니다. 
    date 쿼리 파라미터(YYYY-MM-DD)를 넘기면 특정 날짜를 조회하고, 없으면 오늘 날짜를 조회합니다.
    """
    try:
        schedules = db.get_todays_schedules(target_date=date)
        return {
            "message": "조회 성공",
            "count": len(schedules),
            "data": schedules
        }
    except Exception as e:
        logger.error(f"일정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail="일정을 불러오는 중 서버 내부 오류가 발생했습니다."
        )

# 프롬프트 입력 화면
@app.get("/", summary="입력창 화면")
async def serve_index():
    """기본 주소로 접속하면 index.html을 보여줍니다."""
    return FileResponse("index.html")

# 상황판 화면
@app.get("/dashboard.html", summary="상황판 화면")
async def serve_dashboard():
    """/dashboard.html로 접속하면 상황판을 보여줍니다."""
    return FileResponse("dashboard.html")