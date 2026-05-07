import logging
import secrets
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from app.core.config import settings
from app.core.auth import SESSION_COOKIE_NAME, create_session, require_session
from app.db.repos.user import UserRepository
from app.db.deps import get_user_repo
import app.services.kakao_oauth as kakao_oauth
from app.services.kakao_oauth import KakaoOAuthError
from app.services.kakao_whitelist import find_whitelisted_user


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])

KAKAO_STATE_COOKIE = "yjs_kakao_oauth_state"
KAKAO_NEXT_COOKIE = "yjs_kakao_oauth_next"
KAKAO_OAUTH_COOKIE_MAX_AGE = 600


def _kakao_config_ok() -> bool:
    return bool((settings.KAKAO_REST_API_KEY or "").strip() and (settings.KAKAO_REDIRECT_URI or "").strip())


def _sanitize_next(raw: Optional[str]) -> str:
    if not raw or not isinstance(raw, str):
        return "/dashboard.html"
    s = raw.strip()
    if not s.startswith("/") or s.startswith("//"):
        return "/dashboard.html"
    return s


@router.get("/kakao/login")
def kakao_login(next: str = "/dashboard.html"):
    if not _kakao_config_ok():
        raise HTTPException(
            status_code=503,
            detail="카카오 로그인이 설정되지 않았습니다. KAKAO_REST_API_KEY와 KAKAO_REDIRECT_URI를 확인하세요.",
        )
    state = secrets.token_urlsafe(16)
    dest = _sanitize_next(next)
    url = kakao_oauth.build_authorize_url(state)
    r = RedirectResponse(url=url, status_code=302)
    r.set_cookie(KAKAO_STATE_COOKIE, state, max_age=KAKAO_OAUTH_COOKIE_MAX_AGE, path="/",
                 httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)
    r.set_cookie(KAKAO_NEXT_COOKIE, dest, max_age=KAKAO_OAUTH_COOKIE_MAX_AGE, path="/",
                 httponly=True, samesite="lax", secure=settings.COOKIE_SECURE)
    return r


@router.get("/kakao/callback")
def kakao_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    user_repo: UserRepository = Depends(get_user_repo),
):
    next_url = _sanitize_next(request.cookies.get(KAKAO_NEXT_COOKIE))

    def _fail_redirect(query: str) -> RedirectResponse:
        r = RedirectResponse(url=f"{next_url}{query}", status_code=302)
        r.delete_cookie(KAKAO_STATE_COOKIE, path="/")
        r.delete_cookie(KAKAO_NEXT_COOKIE, path="/")
        return r

    if error:
        msg = quote((error_description or error or "cancelled")[:200], safe="")
        return _fail_redirect(f"?kakao_error={msg}")

    cookie_state = request.cookies.get(KAKAO_STATE_COOKIE)
    if not state or not cookie_state or state != cookie_state:
        return _fail_redirect("?kakao_error=state")

    try:
        token_payload = kakao_oauth.fetch_oauth_token(code)
        access_token = str(token_payload.get("access_token") or "")
        kakao_id = kakao_oauth.fetch_kakao_user_id(access_token)
    except KakaoOAuthError as e:
        return _fail_redirect(f"?kakao_error={quote(str(e), safe='')}")

    entry = find_whitelisted_user(kakao_id)
    if not entry:
        access_row = user_repo.get_login_access_by_kakao_id(kakao_id)
        if access_row and access_row.get("status") == "approved":
            entry = {
                "user_id": str(access_row.get("user_id") or f"kakao_{kakao_id}"),
                "user_name": str(access_row.get("user_name") or f"kakao_{kakao_id}"),
                "role": str(access_row.get("role") or "worker"),
            }
        else:
            user_repo.upsert_login_access_request(kakao_id, note="카카오 로그인 승인 대기")
            logger.info("카카오 로그인 승인 대기 등록: kakao_id=%s", kakao_id)
            return _fail_redirect("?kakao_denied=pending")

    try:
        user_repo.ensure_oauth_user(entry["user_id"], entry["user_name"], entry["role"])
    except ValueError:
        return _fail_redirect("?kakao_error=user")

    device = (request.headers.get("user-agent") or "kakao-oauth")[:500]
    session_id = create_session(user_repo, user_id=entry["user_id"], device_name=device)

    r = RedirectResponse(url=next_url, status_code=302)
    r.delete_cookie(KAKAO_STATE_COOKIE, path="/")
    r.delete_cookie(KAKAO_NEXT_COOKIE, path="/")
    r.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return r


@router.post("/logout")
def logout(
    response: Response,
    session=Depends(require_session),
    user_repo: UserRepository = Depends(get_user_repo),
):
    user_repo.delete_session(session["session_id"])
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax", secure=settings.COOKIE_SECURE)
    return {"message": "로그아웃되었습니다."}


@router.get("/me")
def me(session=Depends(require_session)):
    return {
        "user_id": session["user_id"],
        "role": session["role"],
        "device_name": session["device_name"],
    }
