"""카카오 로그인용 토큰 교환 및 사용자 ID 조회 (표준 라이브러리만 사용)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class KakaoOAuthError(Exception):
    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def fetch_oauth_token(authorization_code: str) -> Dict[str, Any]:
    """authorization_code 로 액세스 토큰 JSON을 받는다."""
    if not authorization_code.strip():
        raise KakaoOAuthError("인가 코드가 없습니다.")
    body: Dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": settings.KAKAO_REDIRECT_URI,
        "code": authorization_code,
    }
    secret = (settings.KAKAO_CLIENT_SECRET or "").strip()
    if secret:
        body["client_secret"] = secret
    data = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            parsed = json.loads(err_body)
            msg = parsed.get("error_description") or parsed.get("error") or err_body
        except Exception:
            msg = str(e)
        logger.warning("카카오 토큰 요청 실패: %s", msg)
        raise KakaoOAuthError(f"카카오 토큰 요청 실패: {msg}", status=getattr(e, "code", None)) from e
    except urllib.error.URLError as e:
        logger.warning("카카오 토큰 네트워크 오류: %s", e)
        raise KakaoOAuthError("카카오 서버에 연결할 수 없습니다.") from e

    parsed = json.loads(raw)
    if "access_token" not in parsed:
        raise KakaoOAuthError("카카오 응답에 access_token이 없습니다.")
    return parsed


def fetch_kakao_user_id(access_token: str) -> str:
    """액세스 토큰으로 /v2/user/me 에서 숫자 id를 문자열로 반환."""
    token = (access_token or "").strip()
    if not token:
        raise KakaoOAuthError("액세스 토큰이 없습니다.")
    req = urllib.request.Request(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        logger.warning("카카오 사용자 정보 요청 HTTP 오류: %s", e)
        raise KakaoOAuthError("카카오 사용자 정보를 가져오지 못했습니다.", status=getattr(e, "code", None)) from e
    except urllib.error.URLError as e:
        logger.warning("카카오 사용자 정보 네트워크 오류: %s", e)
        raise KakaoOAuthError("카카오 서버에 연결할 수 없습니다.") from e

    data = json.loads(raw)
    kid = data.get("id")
    if kid is None:
        raise KakaoOAuthError("카카오 사용자 ID를 확인할 수 없습니다.")
    return str(int(kid))


def build_authorize_url(state: str) -> str:
    q = urllib.parse.urlencode(
        {
            "client_id": settings.KAKAO_REST_API_KEY,
            "redirect_uri": settings.KAKAO_REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
    )
    return f"https://kauth.kakao.com/oauth/authorize?{q}"
