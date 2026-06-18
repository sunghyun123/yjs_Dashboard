# app/services/weather_service.py
"""현장 날씨 위젯 데이터 제공.

기상청 API허브(apihub.kma.go.kr) "단기예보조회(getVilageFcst)" 한 가지만 사용한다.
  - 현재값: 현재 시각에 가장 가까운 예보 슬롯의 기온/풍속/습도/하늘상태/강수확률
  - 예보: 향후 3일 최저/최고/대표 하늘상태

초단기실황(getUltraSrtNcst)은 apihub에서 별도 활용신청이 필요하므로 의존하지 않는다.
미세먼지(dust)는 에어코리아(별도 포털/키)가 필요하므로 생략하고 습도로 대체한다.
"""
from __future__ import annotations

import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo(settings.APP_TIMEZONE or "Asia/Seoul")
except Exception:  # pragma: no cover - 폴백
    _KST = None

logger = logging.getLogger(__name__)

_BASE = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0"
_VILAGE_BASE_TIMES = [2, 5, 8, 11, 14, 17, 20, 23]
_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
_CACHE_TTL_SEC = 600  # 10분 — 프런트가 60초마다 호출하므로 캐시로 상류 호출 보호

# 모듈 레벨 단순 캐시 (단일 지점)
_cache: Dict[str, Any] = {"at": 0.0, "data": None}


def _now() -> datetime:
    return datetime.now(_KST) if _KST else datetime.now()


def _vilage_base(now: datetime) -> tuple[str, str]:
    """단기예보 기준시각: 02/05/08/11/14/17/20/23시 발표, 약 10분 뒤 제공."""
    adj = now - timedelta(minutes=10)
    candidates = [t for t in _VILAGE_BASE_TIMES if t <= adj.hour]
    if candidates:
        return adj.strftime("%Y%m%d"), f"{max(candidates):02d}00"
    prev = adj - timedelta(days=1)
    return prev.strftime("%Y%m%d"), "2300"


def _sky_pty_to_icon(sky: Optional[str], pty: Optional[str]) -> tuple[str, str]:
    """(icon_key, 한글 상태)로 변환. icon_key는 home.js WEATHER_ICONS와 일치."""
    p = str(pty or "0")
    if p == "1":
        return "rain", "비"
    if p == "2":
        return "rain", "비/눈"
    if p == "3":
        return "snow", "눈"
    if p == "4":
        return "shower", "소나기"
    s = str(sky or "1")
    if s == "1":
        return "clear", "맑음"
    if s == "3":
        return "cloudy", "구름많음"
    if s == "4":
        return "overcast", "흐림"
    return "cloudy", "-"


async def _fetch(client: httpx.AsyncClient, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    url = f"{_BASE}/{endpoint}"
    q = {
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "authKey": settings.WEATHER_KMA_AUTH_KEY,
        **params,
    }
    resp = await client.get(url, params=q)
    # 활용신청 누락 등은 HTTP 403 + {"result":{"status":403,...}} 형태로 옴 → 메시지 그대로 노출
    try:
        payload = resp.json()
    except Exception:
        resp.raise_for_status()
        raise RuntimeError("기상청 API 응답을 해석할 수 없습니다.")
    if isinstance(payload, dict) and "result" in payload and "response" not in payload:
        msg = payload["result"].get("message", "기상청 API 오류")
        raise RuntimeError(f"기상청 API 응답 오류({endpoint}): {msg}")
    header = payload["response"]["header"]
    if str(header.get("resultCode")) not in ("00", "0"):
        raise RuntimeError(f"기상청 API 실패({endpoint}): {header.get('resultMsg')}")
    body = payload["response"]["body"]["items"]["item"]
    return body if isinstance(body, list) else [body]


def _build_result(vilage: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    # (날짜,시각)별 카테고리 모으기
    slots: Dict[tuple, Dict[str, str]] = defaultdict(dict)
    for it in vilage:
        slots[(it["fcstDate"], it["fcstTime"])][it["category"]] = it["fcstValue"]

    # ── 현재값: 현재 시각에 가장 가까운(직전 또는 동일) 슬롯 ──
    today = now.strftime("%Y%m%d")
    key_now = (today, f"{now.hour:02d}00")
    past = [k for k in slots if k <= key_now]
    near_key = max(past) if past else (min(slots) if slots else None)
    near = slots.get(near_key, {}) if near_key else {}

    icon, condition = _sky_pty_to_icon(near.get("SKY"), near.get("PTY"))
    temp = _to_num(near.get("TMP"))
    wind = _to_num(near.get("WSD"))
    humidity = _to_num(near.get("REH"))
    pop = _to_num(near.get("POP"))

    # ── 일자별 예보 카드 (오늘 포함 최대 3일) ──
    by_date: Dict[str, Dict[str, str]] = defaultdict(dict)
    temps_by_date: Dict[str, List[float]] = defaultdict(list)
    noon_by_date: Dict[str, Dict[str, str]] = {}
    for (d, t), cats in slots.items():
        if "TMX" in cats:
            by_date[d]["TMX"] = cats["TMX"]
        if "TMN" in cats:
            by_date[d]["TMN"] = cats["TMN"]
        v = _to_num(cats.get("TMP"))
        if v is not None:
            temps_by_date[d].append(v)
        if t in ("1200", "1500"):
            noon_by_date.setdefault(d, cats)

    forecast: List[Dict[str, Any]] = []
    rain_days: List[str] = []
    for d in sorted(by_date)[:3]:
        high = _to_num(by_date[d].get("TMX"))
        if high is None and temps_by_date[d]:
            high = max(temps_by_date[d])
        low = _to_num(by_date[d].get("TMN"))
        if low is None and temps_by_date[d]:
            low = min(temps_by_date[d])
        noon = noon_by_date.get(d, {})
        ic, _cond = _sky_pty_to_icon(noon.get("SKY"), noon.get("PTY"))
        if ic in ("rain", "snow", "shower"):
            rain_days.append(_weekday(d))
        forecast.append({
            "day": _weekday(d),
            "icon": ic,
            "high": _round(high),
            "low": _round(low),
        })

    alert = ""
    if rain_days:
        uniq = list(dict.fromkeys(rain_days))
        alert = f"⚠️ {'·'.join(uniq)}요일 강수 예보 — 옥외 작업 일정 조정 검토"

    return {
        "city": settings.WEATHER_CITY_NAME,
        "temp": _round(temp),
        "condition": condition,
        "icon": icon,
        "pop": _round(pop),
        "wind": _round(wind, 1),
        "humidity": _round(humidity),
        "dust": None,  # 에어코리아 키 연동 시 채움
        "forecast": forecast,
        "alert": alert,
    }


def _to_num(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "-", "강수없음", "적설없음"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _round(v: Optional[float], digits: int = 0):
    if v is None:
        return None
    return int(round(v)) if digits == 0 else round(v, digits)


def _weekday(yyyymmdd: str) -> str:
    try:
        d = datetime.strptime(yyyymmdd, "%Y%m%d")
        return _WEEKDAYS[d.weekday()]
    except ValueError:
        return "-"


async def get_current_weather() -> Dict[str, Any]:
    """현장 날씨 데이터를 반환한다. 실패 시 RuntimeError를 던진다(라우터에서 503 처리)."""
    if not settings.WEATHER_KMA_AUTH_KEY:
        raise RuntimeError("WEATHER_KMA_AUTH_KEY 미설정")

    if _cache["data"] is not None and (time.time() - _cache["at"]) < _CACHE_TTL_SEC:
        return _cache["data"]

    now = _now()
    nx, ny = settings.WEATHER_GRID_NX, settings.WEATHER_GRID_NY
    vil_date, vil_time = _vilage_base(now)

    async with httpx.AsyncClient(timeout=10.0) as client:
        vilage = await _fetch(client, "getVilageFcst", {
            "base_date": vil_date, "base_time": vil_time, "nx": nx, "ny": ny,
        })

    result = _build_result(vilage, now)
    _cache["data"] = result
    _cache["at"] = time.time()
    return result
