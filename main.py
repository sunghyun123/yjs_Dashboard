# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
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
from app.api import documents
from app.api import local_apps
from app.db.db_manager import DBManager
from app.services.export_service import DailyExportService
from app.core.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # 최소 보안 헤더. 기존 기능에 영향 없는 범위로만 설정.
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if settings.COOKIE_SECURE:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


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
app.add_middleware(SecurityHeadersMiddleware)
if settings.FORCE_HTTPS_REDIRECT:
    app.add_middleware(HTTPSRedirectMiddleware)

if settings.COOKIE_SECURE is False:
    logger.warning("COOKIE_SECURE=false: 운영 HTTPS 배포에서는 true로 설정하세요.")
if "*" in settings.trusted_host_list:
    logger.warning("ALLOWED_HOSTS='*': 운영 배포에서는 도메인으로 제한하세요.")
if "*" in settings.cors_origin_list:
    logger.warning("ALLOWED_ORIGINS='*': 운영 배포에서는 프런트 도메인으로 제한하세요.")

# --- 라우터 등록 (여기서 분리된 방들을 메인 앱에 연결해 줍니다) ---
app.include_router(schedules.router)
app.include_router(vision.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(local_apps.router)

# --- 프론트엔드 화면 서빙 ---
@app.get("/", summary="기본 상황판 화면", tags=["Pages"])
async def serve_home():
    return FileResponse("dashboard.html")

@app.get("/dashboard.html", summary="상황판 화면", tags=["Pages"])
async def serve_dashboard():
    return FileResponse("dashboard.html")


@app.get("/index.html", summary="채팅 입력 화면", tags=["Pages"])
async def serve_index():
    return FileResponse("index.html")


@app.get("/admin.html", summary="관리자 화면", tags=["Pages"])
async def serve_admin():
    return FileResponse("admin.html")


@app.get("/board.html", summary="레거시 경로 → 상황판 리다이렉트", tags=["Pages"])
async def serve_board():
    return RedirectResponse(url="/dashboard.html", status_code=307)


@app.get("/site.webmanifest", summary="PWA 매니페스트", tags=["Pages"])
async def serve_web_manifest():
    return FileResponse("site.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", summary="서비스 워커(설치용)", tags=["Pages"])
async def serve_service_worker():
    return FileResponse("sw.js", media_type="application/javascript")


@app.get("/icon.svg", summary="PWA 아이콘", tags=["Pages"])
async def serve_app_icon():
    return FileResponse("icon.svg", media_type="image/svg+xml")


@app.get("/dashboard.auth.js", summary="대시보드 인증 스크립트", tags=["Pages"])
async def serve_dashboard_auth_js():
    return FileResponse("dashboard.auth.js", media_type="application/javascript")


@app.get("/dashboard.sidebar.js", summary="대시보드 사이드바 스크립트", tags=["Pages"])
async def serve_dashboard_sidebar_js():
    return FileResponse("dashboard.sidebar.js", media_type="application/javascript")


@app.get("/dashboard.schedule.js", summary="대시보드 일정 스크립트", tags=["Pages"])
async def serve_dashboard_schedule_js():
    return FileResponse("dashboard.schedule.js", media_type="application/javascript")


@app.get("/dashboard.document.js", summary="대시보드 문서 스크립트", tags=["Pages"])
async def serve_dashboard_document_js():
    return FileResponse("dashboard.document.js", media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )