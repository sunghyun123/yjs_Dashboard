# app/api/progress_map.py
"""진행중 공사 지도 데이터 API.

- GET  /api/progress-sites : 로그인 세션이면 조회 (홈 지도 + 관리 페이지 로딩)
- PUT  /api/progress-sites : 관리자만 저장 (관리 페이지)
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import require_admin, require_session
from app.services.progress_sites_service import load_sites, save_sites

router = APIRouter(prefix="/api/progress-sites", tags=["ProgressMap"])


class SiteIn(BaseModel):
    no: str = Field(default="")
    name: str = Field(default="")
    manager: str = Field(default="")
    percent: float = Field(default=0)
    addr: str = Field(default="")
    lat: Optional[float] = Field(default=None)
    lng: Optional[float] = Field(default=None)


class SitesSavePayload(BaseModel):
    month_label: str = Field(default="")
    sites: List[SiteIn] = Field(default_factory=list)


@router.get("")
def get_progress_sites(_session=Depends(require_session)):
    return {"status": "success", **load_sites()}


@router.put("")
def put_progress_sites(payload: SitesSavePayload, _admin=Depends(require_admin)):
    doc = save_sites([s.model_dump() for s in payload.sites], month_label=payload.month_label)
    return {"status": "success", **doc}
