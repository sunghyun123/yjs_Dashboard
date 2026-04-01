# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

# 분리해둔 API 라우터들을 불러옵니다.
from app.api import schedules
from app.api import vision
from app.api import auth
from app.api import admin
from app.db.db_manager import DBManager
from app.services.export_service import DailyExportService
from app.core.config import settings

logger = logging.getLogger(__name__)

async def daily_export_loop():
    """주기적으로 전일 백업을 점검/실행한다."""
    db = DBManager(db_path=settings.sqlite_db_path) # DB 초기화
    svc = DailyExportService(db=db) # 내보내기 서비스 초기화
    while True:
        try:
            result = svc.export_yesterday_if_needed()
            if not result.get("skipped"):
                logger.info(f"전일 백업데이터 생성 완료: {result}")
            archive_result = svc.archive_old_daily_reports(keep_days=90)
            if archive_result.get("archived_count", 0) > 0:
                logger.info(f"백업 아카이브 정리 완료: {archive_result}")
        except Exception as e:
            logger.error(f"전일 백업데이터 자동 점검 실패: {e}")
        # 1시간마다 점검
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(daily_export_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="현장 작업자의 비정형 텍스트 및 이미지를 분석하여 상황판에 연동합니다.",
    version="1.1.0",
    lifespan=lifespan
)

allow_origins = settings.cors_origin_list
allow_credentials = "*" not in allow_origins

app.add_middleware( # 모든 경로에 대해 CORS 허용
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

# --- 라우터 등록 (여기서 분리된 방들을 메인 앱에 연결해 줍니다) ---
app.include_router(schedules.router)
app.include_router(vision.router)
app.include_router(auth.router)
app.include_router(admin.router)

# --- 프론트엔드 화면 서빙 ---
@app.get("/", summary="입력창 화면", tags=["Pages"])
async def serve_index():
    return FileResponse("index.html")

@app.get("/dashboard.html", summary="상황판 화면", tags=["Pages"])
async def serve_dashboard():
    return FileResponse("dashboard.html")


@app.get("/admin.html", summary="관리자 화면", tags=["Pages"])
async def serve_admin():
    return FileResponse("admin.html")


@app.get("/board.html", summary="레거시 경로 → 상황판 리다이렉트", tags=["Pages"])
async def serve_board():
    return RedirectResponse(url="/dashboard.html", status_code=307)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )