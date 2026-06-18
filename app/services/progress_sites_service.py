# app/services/progress_sites_service.py
"""진행중 공사 지도용 사이트 목록 저장소.

DB가 아니라 JSON 파일(data/progress_sites.json)에 보관한다.
- 월 1회 갱신되는 '스냅샷 문서' 성격이라 관계형보다 파일이 단순하고 깃 리뷰에 친화적.
- 위경도(lat/lng)는 관리 페이지의 지도에서 핀을 끌어 지정하면 채워지고,
  비어 있으면 프런트가 주소(addr) → 자동 지오코딩한다.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo(settings.APP_TIMEZONE or "Asia/Seoul")
except Exception:  # pragma: no cover - 폴백
    _KST = None

_DATA_PATH = Path("data/progress_sites.json")


def _now_iso() -> str:
    now = datetime.now(_KST) if _KST else datetime.now()
    return now.strftime("%Y-%m-%d %H:%M")


def _empty_doc() -> Dict[str, Any]:
    return {"updated_at": "", "month_label": "", "sites": []}


def load_sites() -> Dict[str, Any]:
    """저장된 문서를 그대로 반환한다. 파일이 없거나 깨졌으면 빈 문서."""
    try:
        with _DATA_PATH.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return _empty_doc()
    except (json.JSONDecodeError, OSError):
        return _empty_doc()
    if not isinstance(doc, dict):
        return _empty_doc()
    doc.setdefault("updated_at", "")
    doc.setdefault("month_label", "")
    if not isinstance(doc.get("sites"), list):
        doc["sites"] = []
    return doc


def _num(v: Any) -> Optional[float]:
    try:
        if v in (None, ""):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _clean_site(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None  # 공사명이 없으면 핀의 의미가 없으므로 제외

    lat = _num(raw.get("lat"))
    lng = _num(raw.get("lng"))
    # 대한민국 범위 밖 좌표는 버려 자동 지오코딩으로 폴백시킨다(오입력 방어).
    if lat is not None and not (33.0 <= lat <= 39.5):
        lat = None
    if lng is not None and not (124.0 <= lng <= 132.0):
        lng = None
    if lat is None or lng is None:
        lat = lng = None

    pct = _num(raw.get("percent"))
    return {
        "no": str(raw.get("no") or "").strip(),
        "name": name,
        "manager": str(raw.get("manager") or "").strip(),
        "percent": pct if pct is not None else 0,
        "addr": str(raw.get("addr") or "").strip(),
        "lat": lat,
        "lng": lng,
    }


def save_sites(sites: List[Dict[str, Any]], month_label: str = "") -> Dict[str, Any]:
    """사이트 목록을 정규화해 원자적으로 저장하고, 저장된 문서를 반환한다."""
    cleaned: List[Dict[str, Any]] = []
    for raw in (sites or []):
        c = _clean_site(raw)
        if c:
            cleaned.append(c)

    doc = {
        "updated_at": _now_iso(),
        "month_label": str(month_label or "").strip(),
        "sites": cleaned,
    }

    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 원자적 쓰기: 임시파일에 기록 후 교체 → 중간에 죽어도 기존 파일 보존
    fd, tmp = tempfile.mkstemp(dir=str(_DATA_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _DATA_PATH)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return doc
