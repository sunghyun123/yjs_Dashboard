# app/core/auth.py
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from fastapi import Cookie, HTTPException, Depends

from app.core.config import settings
from app.db.repos.user import UserRepository
from app.db.deps import get_user_repo


SESSION_COOKIE_NAME = "yjs_session_id"


def create_session(user_repo: UserRepository, user_id: str, device_name: str) -> str:
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.SESSION_TTL_DAYS)
    user_repo.create_session(session_id=session_id, user_id=user_id,
                              device_name=device_name, expires_at=expires_at.isoformat())
    return session_id


def require_session(
    session_id: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    user_repo: UserRepository = Depends(get_user_repo),
) -> Dict[str, Any]:
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    session = user_repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="세션이 만료되었거나 유효하지 않습니다.")
    return session


def require_admin(session: Dict[str, Any] = Depends(require_session)) -> Dict[str, Any]:
    if session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return session
