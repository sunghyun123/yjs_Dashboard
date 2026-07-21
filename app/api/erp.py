# app/api/erp.py
import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_session
from app.core.config import settings
from app.db.deps import get_monthly_progress_repo
from app.db.repos.monthly_progress import MonthlyProgressRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/erp", tags=["ERP"])


def _normalize_monthly_kpi(payload: Dict[str, Any]) -> Dict[str, Any]:
    amounts = payload.get("amounts") if isinstance(payload.get("amounts"), dict) else {}
    formatted = payload.get("formatted") if isinstance(payload.get("formatted"), dict) else {}

    return {
        "status": "success",
        "label": payload.get("label") or "",
        "amounts": {
            "monthlyRevenue": amounts.get("monthlyRevenue"),
            "monthlyInput": amounts.get("monthlyInput"),
            "monthlyProfit": amounts.get("monthlyProfit"),
        },
        "formatted": {
            "monthlyRevenue": formatted.get("monthlyRevenue") or "",
            "monthlyInput": formatted.get("monthlyInput") or "",
            "monthlyProfit": formatted.get("monthlyProfit") or "",
        },
        "updatedAt": payload.get("updatedAt") or "",
    }


@router.get("/monthly-kpi")
async def get_monthly_kpi(_session=Depends(require_session)):
    url = (settings.ERP_MONTHLY_KPI_URL or "").strip()
    token = (settings.ERP_DASHBOARD_API_KEY or "").strip()
    if not url or not token:
        raise HTTPException(status_code=503, detail="ERP KPI API is not configured.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("ERP KPI API returned a non-object response.")
        return _normalize_monthly_kpi(body)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("ERP monthly KPI lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="ERP KPI data is unavailable.")


def _as_int(value: Any) -> int:
    # ERP가 숫자를 문자열/실수로 보내도 타일이 깨지지 않게 정수로 강제, 실패 시 0
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _as_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalize_materials(payload: Dict[str, Any]) -> Dict[str, Any]:
    # 방어적 재포장: 알려진 키만 뽑아 타입 강제 + 배열 보장 → home.js는 모양 방어 불필요.
    # 깨진/부분 응답이 와도 렌더 계약(stats·cable.groups·etc.groups)은 항상 성립한다.
    cable = payload.get("cable") if isinstance(payload.get("cable"), dict) else {}
    stats = cable.get("stats") if isinstance(cable.get("stats"), dict) else {}
    etc = payload.get("etc") if isinstance(payload.get("etc"), dict) else {}

    def norm_chip(chip: Dict[str, Any]) -> Dict[str, Any]:
        maker = chip.get("maker")  # null은 의미 있음(제조표기 없음) — 보존
        return {
            "remaining": _as_int(chip.get("remaining")),
            "count": _as_int(chip.get("count")),
            "maker": str(maker) if maker is not None else None,
            "remnant": bool(chip.get("remnant")),
            "shipping": bool(chip.get("shipping")),
        }

    def norm_line(line: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "code": _as_str(line.get("code")),
            "totalRemaining": _as_int(line.get("totalRemaining")),
            "drumCount": _as_int(line.get("drumCount")),
            "chips": [norm_chip(c) for c in _as_list(line.get("chips")) if isinstance(c, dict)],
        }

    def norm_cable_group(group: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "voltage": _as_str(group.get("voltage")),
            "lines": [norm_line(l) for l in _as_list(group.get("lines")) if isinstance(l, dict)],
        }

    def norm_etc_item(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": _as_str(item.get("name")),
            "count": _as_int(item.get("count")),
            "unit": _as_str(item.get("unit")),
        }

    def norm_etc_group(group: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "category": _as_str(group.get("category")),
            "items": [norm_etc_item(i) for i in _as_list(group.get("items")) if isinstance(i, dict)],
        }

    return {
        "status": "success",
        "cable": {
            # 재고 타일은 stats 직접 사용 — 출고중 제외한 창고 실재고(lines에서 재계산 금지)
            "stats": {
                "highVoltageStock": _as_int(stats.get("highVoltageStock")),
                "lowVoltageStock": _as_int(stats.get("lowVoltageStock")),
                "remnantDrums": _as_int(stats.get("remnantDrums")),
            },
            "groups": [norm_cable_group(g) for g in _as_list(cable.get("groups")) if isinstance(g, dict)],
        },
        "etc": {
            "groups": [norm_etc_group(g) for g in _as_list(etc.get("groups")) if isinstance(g, dict)],
        },
        "updatedAt": _as_str(payload.get("updatedAt")),
    }


@router.get("/materials")
async def get_materials(_session=Depends(require_session)):
    url = (settings.ERP_MATERIALS_URL or "").strip()
    token = (settings.ERP_DASHBOARD_API_KEY or "").strip()
    if not url or not token:
        raise HTTPException(status_code=503, detail="ERP materials API is not configured.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("ERP materials API returned a non-object response.")
        return _normalize_materials(body)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("ERP materials lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="ERP materials data is unavailable.")


@router.get("/monthly-progress-config")
def get_monthly_progress_config(
    month: str = "",
    _session=Depends(require_session),
    repo: MonthlyProgressRepository = Depends(get_monthly_progress_repo),
):
    return {"status": "success", "data": repo.get_config(month or None)}
