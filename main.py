# app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from app.api import schedules
from app.api import vision
from app.api import auth
from app.api import admin
from app.db.migrations import run_migrations
from app.services.export_service import DailyExportService
from app.core.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if settings.COOKIE_SECURE:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


async def daily_export_loop():
    """주기적으로 전일 백업을 점검/실행한다."""
    svc = DailyExportService(db_path=settings.sqlite_db_path)
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
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations(settings.sqlite_db_path)
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
    version="1.2.0",
    lifespan=lifespan,
)

allow_origins = settings.cors_origin_list
allow_credentials = "*" not in allow_origins

app.add_middleware(
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

app.include_router(schedules.router)
app.include_router(vision.router)
app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/", summary="기본 운영 홈 화면", tags=["Pages"])
async def serve_home():
    return FileResponse("web/home.html")

@app.get("/dashboard.html", summary="상황판 화면", tags=["Pages"])
async def serve_dashboard():
    return FileResponse("web/dashboard.html")

@app.get("/home.html", summary="운영 홈 화면", tags=["Pages"])
async def serve_home_page():
    return FileResponse("web/home.html")

@app.get("/index.html", summary="채팅 입력 화면", tags=["Pages"])
async def serve_index():
    return FileResponse("web/index.html")

@app.get("/admin.html", summary="관리자 화면", tags=["Pages"])
async def serve_admin():
    return FileResponse("web/admin.html")

@app.get("/board.html", summary="레거시 경로 → 상황판 리다이렉트", tags=["Pages"])
async def serve_board():
    return RedirectResponse(url="/dashboard.html", status_code=307)

@app.get("/site.webmanifest", summary="PWA 매니페스트", tags=["Pages"])
async def serve_web_manifest():
    return FileResponse("web/site.webmanifest", media_type="application/manifest+json")

@app.get("/sw.js", summary="서비스 워커(설치용)", tags=["Pages"])
async def serve_service_worker():
    return FileResponse("web/sw.js", media_type="application/javascript")

@app.get("/icon.svg", summary="PWA 아이콘", tags=["Pages"])
async def serve_app_icon():
    return FileResponse("web/icon.svg", media_type="image/svg+xml")

@app.get("/dashboard.common.js", summary="대시보드 공통 유틸 스크립트", tags=["Pages"])
async def serve_dashboard_common_js():
    return FileResponse("web/dashboard.common.js", media_type="application/javascript")

@app.get("/dashboard.auth.js", summary="대시보드 인증 스크립트", tags=["Pages"])
async def serve_dashboard_auth_js():
    return FileResponse("web/dashboard.auth.js", media_type="application/javascript")

@app.get("/dashboard.sidebar.js", summary="대시보드 사이드바 스크립트", tags=["Pages"])
async def serve_dashboard_sidebar_js():
    return FileResponse("web/dashboard.sidebar.js", media_type="application/javascript")

@app.get("/dashboard.schedule.js", summary="대시보드 일정 스크립트", tags=["Pages"])
async def serve_dashboard_schedule_js():
    return FileResponse("web/dashboard.schedule.js", media_type="application/javascript")

@app.get("/home.js", summary="홈 화면 스크립트", tags=["Pages"])
async def serve_home_js():
    return FileResponse("web/home.js", media_type="application/javascript")

@app.get("/uploads/photos/{file_path:path}", summary="첨부 사진 파일 서빙", tags=["Pages"])
async def serve_upload_photo(file_path: str):
    safe = Path(settings.UPLOADS_DIR) / Path(file_path)
    resolved = safe.resolve()
    base = Path(settings.UPLOADS_DIR).resolve()
    if not str(resolved).startswith(str(base)):
        raise HTTPException(status_code=403, detail="접근이 거부되었습니다.")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(str(resolved))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
