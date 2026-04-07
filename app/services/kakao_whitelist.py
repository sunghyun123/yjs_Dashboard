"""레포지토리 내 JSON 화이트리스트로 허용 카카오 사용자를 판별한다."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalize_role(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    return "admin" if s == "admin" else "worker"


def load_whitelist_entries() -> List[Dict[str, str]]:
    path = Path(settings.KAKAO_WHITELIST_PATH)
    if not path.is_file():
        logger.warning("카카오 화이트리스트 파일이 없습니다: %s", path)
        return []
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("화이트리스트 JSON 읽기 실패: %s", e)
        return []

    users = data.get("users")
    if not isinstance(users, list):
        return []

    out: List[Dict[str, str]] = []
    for item in users:
        if not isinstance(item, dict):
            continue
        kid = str(item.get("kakao_id", "")).strip()
        uid = str(item.get("user_id", "")).strip()
        if not kid or not uid:
            continue
        name = str(item.get("user_name", "")).strip() or uid
        role = _normalize_role(item.get("role"))
        out.append(
            {
                "kakao_id": kid,
                "user_id": uid,
                "user_name": name,
                "role": role,
            }
        )
    return out


def find_whitelisted_user(kakao_id: str) -> Optional[Dict[str, str]]:
    kid = str(kakao_id or "").strip()
    if not kid:
        return None
    for row in load_whitelist_entries():
        if row["kakao_id"] == kid:
            return row
    return None
