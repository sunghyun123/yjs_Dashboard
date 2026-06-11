# app/services/erp_sync_service.py
import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

_ERP_URL = "https://erp.yjsboard.com/api/dashboard-sync"
_AUTH_TOKEN = "a6ea8e964d6c5529bf16d101bc9631bafd22862711721b83e7eaabceda79ca07"
_TIMEOUT = 10.0


def sync_constructions(records: List[Dict[str, Any]]) -> None:
    """공사 진행 목록을 ERP 서버로 전송한다. 실패해도 예외를 발생시키지 않는다."""
    items = [
        {
            "지중no": str(r.get("work_code") or "").strip(),
            "공사명": str(r.get("task") or "").strip(),
            "진행날짜": str(r.get("date") or "").strip(),
        }
        for r in records
        if str(r.get("work_code") or "").strip() and str(r.get("date") or "").strip()
    ]
    if not items:
        return

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _ERP_URL,
                headers={
                    "Authorization": f"Bearer {_AUTH_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"constructions": items},
            )
        if resp.status_code == 401:
            logger.error("ERP 동기화 인증 실패 (401): %s", resp.text[:300])
        elif resp.status_code >= 500:
            logger.error("ERP 동기화 서버 오류 (%d): %s", resp.status_code, resp.text[:300])
        else:
            try:
                body = resp.json()
            except Exception:
                body = {}
            logger.info(
                "ERP 동기화 완료 — inserted=%s skipped=%s",
                body.get("inserted", "?"),
                body.get("skipped", "?"),
            )
    except Exception as exc:
        logger.error("ERP 동기화 요청 실패: %s", exc)
