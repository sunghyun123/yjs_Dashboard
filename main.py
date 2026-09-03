# app/main.py
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress

from app.api import schedules
from app.api import vision
from app.api import auth
from app.api import admin
from app.api import progress_map
from app.api import erp
from app.db.migrations import run_migrations
from app.db.repos.user import UserRepository
from app.services.export_service import DailyExportService
from app.core.config import settings
from app.core.auth import require_session, SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

# 액세스 로그 전용 로거. uvicorn 기본 access 로그(access_log=False)를 대체한다.
# root 로거에 핸들러가 없어도 INFO가 확실히 stderr→journald로 나가도록 직접 핸들러를 단다.
access_logger = logging.getLogger("yjs.access")
if not access_logger.handlers:
    _access_handler = logging.StreamHandler()
    _access_handler.setFormatter(logging.Formatter("%(levelname)s [access] %(message)s"))
    access_logger.addHandler(_access_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False


class AccessLogMiddleware(BaseHTTPMiddleware):
    """요청마다 세션 쿠키로 사용자를 식별해 한 줄 액세스 로그를 남긴다.

    로그 예시: `1.235.19.128 user=hong(worker) GET /api/schedules/today 200 3.1ms`
    - 세션 조회 결과는 30초 캐시(한 페이지가 동시에 여러 요청을 쏘므로 DB 조회를 줄임).
    - 미인증 요청은 user=anon, 만료/위조 세션은 user=invalid-session.
    """

    _SESSION_CACHE_TTL = 30.0  # 초
    _CACHE_MAX = 512

    def __init__(self, app):
        super().__init__(app)
        self._user_repo = UserRepository(settings.sqlite_db_path)
        self._session_cache: dict[str, tuple[float, str]] = {}

    def _resolve_user(self, session_id) -> str:
        if not session_id:
            return "anon"
        now = time.monotonic()
        cached = self._session_cache.get(session_id)
        if cached and now - cached[0] < self._SESSION_CACHE_TTL:
            return cached[1]
        try:
            session = self._user_repo.get_session(session_id)
        except Exception:
            return "anon"  # 로그 때문에 요청을 깨뜨리지 않는다.
        if not session:
            label = "invalid-session"
        else:
            label = f"{session.get('user_id')}({session.get('role')})"
        if len(self._session_cache) >= self._CACHE_MAX:
            self._session_cache.clear()
        self._session_cache[session_id] = (now, label)
        return label

    async def dispatch(self, request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000.0
        try:
            user = self._resolve_user(request.cookies.get(SESSION_COOKIE_NAME))
            client_ip = request.client.host if request.client else "-"
            query = f"?{request.url.query}" if request.url.query else ""
            access_logger.info(
                "%s user=%s %s %s%s %s %.1fms",
                client_ip, user, request.method, request.url.path, query,
                response.status_code, elapsed_ms,
            )
        except Exception:  # 로깅 실패가 응답을 막지 않도록 방어
            logger.exception("액세스 로그 기록 실패")
        return response


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
# 마지막에 추가 = 최외곽 → 최종 상태코드와 전체 소요시간을 정확히 집계한다.
app.add_middleware(AccessLogMiddleware)

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
app.include_router(progress_map.router)
app.include_router(erp.router)


@app.get("/api/public-config", summary="프런트 공개 설정값(지도 키 등)", tags=["Pages"])
async def public_config(_session=Depends(require_session)):
    """로그인 세션에 한해 프런트가 필요로 하는 공개 설정값을 내려준다.
    카카오맵 JS 키는 도메인 제한이 걸린 공개 키이며, 코드/깃에 하드코딩하지 않기 위해 env에서 주입한다."""
    return {"kakaoMapJsKey": settings.KAKAO_MAP_JS_KEY}


@app.get("/api/weather/current", summary="현장 날씨(기상청 단기예보)", tags=["Pages"])
async def weather_current(_session=Depends(require_session)):
    """홈 화면 현장 날씨 위젯용. 키 미설정/상류 오류 시 503 → 프런트는 플레이스홀더 표시."""
    from app.services.weather_service import get_current_weather
    try:
        return await get_current_weather()
    except Exception as e:
        logger.warning(f"날씨 조회 실패: {e}")
        raise HTTPException(status_code=503, detail="날씨 정보를 불러오지 못했습니다.")


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

@app.get("/map-admin.html", summary="진행중 공사 지도 관리 화면", tags=["Pages"])
async def serve_map_admin():
    return FileResponse("web/map-admin.html")

@app.get("/map-admin.js", summary="공사 지도 관리 스크립트", tags=["Pages"])
async def serve_map_admin_js():
    return FileResponse("web/map-admin.js", media_type="application/javascript")

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

@app.get("/dashboard.holidays.js", summary="대시보드 공휴일 스크립트", tags=["Pages"])
async def serve_dashboard_holidays_js():
    return FileResponse("web/dashboard.holidays.js", media_type="application/javascript")

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
        access_log=False,  # 기본 액세스 로그 대신 AccessLogMiddleware(사용자명 포함) 사용
    )
