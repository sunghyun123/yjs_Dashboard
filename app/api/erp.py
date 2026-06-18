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


@router.get("/monthly-progress-config")
def get_monthly_progress_config(
    month: str = "",
    _session=Depends(require_session),
    repo: MonthlyProgressRepository = Depends(get_monthly_progress_repo),
):
    return {"status": "success", "data": repo.get_config(month or None)}
