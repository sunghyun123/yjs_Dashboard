# app/api/erp.py
import logging
import re
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_session
from app.core.config import settings
from app.db.deps import get_monthly_progress_repo
from app.db.repos.monthly_progress import MonthlyProgressRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/erp", tags=["ERP"])


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


def _as_day_list(value: Any) -> list:
    # 화면에 '일'로 찍히는 값이라 1~31 밖은 아예 버린다(표기가 깨지느니 안 보이는 편이 낫다)
    out = []
    for item in _as_list(value):
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 31:
            out.append(day)
    return out


def _as_day(value: Any) -> Optional[int]:
    # 정산 행의 '일' 하나 — 1~31 밖이거나 숫자가 아니면 None(표기가 깨지느니 비워 둔다)
    days = _as_day_list([value])
    return days[0] if days else None


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MONTH_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def _as_date(value: Any) -> Optional[str]:
    # 'YYYY-MM-DD' 모양만 통과 — 화면에 찍히는 값이라 태그로 해석될 문자열이 들어올 자리를 남기지 않는다
    s = _as_str(value)
    return s if _DATE_RE.fullmatch(s) else None


def _as_date_list(value: Any) -> list:
    return [d for d in (_as_date(item) for item in _as_list(value)) if d]


def _as_month(value: Any) -> Optional[str]:
    # 목표 행을 고르는 열쇠('YYYY-MM')로 쓰인다 — 모양이 틀리면 None(화면은 달력 월로 돌아간다)
    s = _as_str(value)
    return s if _MONTH_RE.fullmatch(s) else None


def _construction_managers(item: Dict[str, Any], amount: int) -> Optional[list]:
    """
    시공 행의 담당별(2026-10-29). 시공 담당은 ERP 공사이력.담당공무_id 한 곳에서 정하고, 대시보드는 그 나눔을 그대로 쓴다.
    없으면(옛 ERP) None — home.js 가 그 행만 옛 규칙(목표 행 → 계획외 지정)으로 나눈다.
    담당별 합이 공사 금액과 다르면 그 행의 담당별만 버린다(None): 담당자 칸의 합이 도넛과 어긋나는 것보다
    옛 규칙으로 나누는 쪽이 낫고, 섹션 전체를 버리면 도넛까지 대체값으로 떨어진다.
    """
    raw = item.get("담당별")
    if not isinstance(raw, list):
        return None
    managers = [
        {
            "name": _as_str(m.get("담당")),  # '' = 담당 미지정
            "amountThousand": _as_int(m.get("금액천원")),
            "dates": _as_date_list(m.get("날짜")),
            "nightDates": _as_date_list(m.get("야간날짜")),
        }
        for m in raw
        if isinstance(m, dict)
    ]
    if len(managers) != len(raw) or sum(m["amountThousand"] for m in managers) != amount:
        logger.warning("ERP KPI split.construction %s: 담당별이 공사 금액과 맞지 않아 버린다", _as_str(item.get("지중no")))
        return None
    return managers


def _construction_row(item: Dict[str, Any]) -> Dict[str, Any]:
    amount = _as_int(item.get("금액천원"))
    return {
        "jijungNo": _as_str(item.get("지중no")),
        "name": _as_str(item.get("공사명")),
        "amountThousand": amount,
        "days": _as_day_list(item.get("일자")),
        "nightDays": _as_day_list(item.get("야간일자")),
        # split 은 금요일 기준 주차로 잘라 달을 넘나든다(9월 실적에 8/31) — '일'만으로는 달을 모른다
        "dates": _as_date_list(item.get("날짜")),
        "nightDates": _as_date_list(item.get("야간날짜")),
        # 허용목록이라 이 줄이 없으면 ERP 가 보낸 담당별이 브라우저에 도착하지 않는다
        "managers": _construction_managers(item, amount),
    }


def _settlement_row(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jijungNo": _as_str(item.get("지중no")),
        "name": _as_str(item.get("공사명")),
        "kind": _as_str(item.get("구분")),
        "day": _as_day(item.get("일")),
        "date": _as_date(item.get("날짜")),
        "amountThousand": _as_int(item.get("금액천원")),
        # 정산 담당(2026-10-29) = ERP 수주.정산담당자_id. '' = 정산 미지정, None = 옛 ERP(칸 없음 → home.js 가 옛 규칙으로 나눔).
        # 허용목록이라 이 줄이 없으면 ERP 가 보낸 담당이 브라우저에 도착하지 않는다
        "manager": _as_str(item.get("담당")) if "담당" in item else None,
    }


def _normalize_section(raw: Any, to_row, label: str) -> Optional[Dict[str, Any]]:
    """
    '행 목록 + 합계' 한 섹션을 방어적으로 재포장한다 (breakdown · split.construction · split.settlement 공통).

    ⚠️ 이 섹션들의 존재 이유가 "표의 합계 == 화면의 숫자"이므로, 재포장 과정에서 행이
       한 줄이라도 유실되면 그 순간 표는 조용히 틀린 표가 된다. 그래서 총액을 ERP가
       보낸 값으로 믿지 않고 **재포장된 행들을 직접 더해서** 만들고, ERP가 말한 총액과
       다르면 섹션을 통째로 버린다(None). 모자란 표를 보여주느니 없는 게 낫다.
    """
    if not isinstance(raw, dict):
        return None
    rows_raw = _as_list(raw.get("rows"))
    rows = [to_row(item) for item in rows_raw if isinstance(item, dict)]
    if len(rows) != len(rows_raw):
        logger.warning("ERP KPI %s: %d개 행 중 %d개만 읽혀 버린다", label, len(rows_raw), len(rows))
        return None

    total = sum(row["amountThousand"] for row in rows)
    reported = raw.get("totalThousand")
    if reported is not None and _as_int(reported) != total:
        logger.warning("ERP KPI %s 합계 불일치(ERP %s / 행 합 %s) — 버린다", label, reported, total)
        return None
    return {"rows": rows, "totalThousand": total}


def _normalize_breakdown(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # 기존 칸(시공 + 준공 보정). 대시보드가 split 으로 옮겨간 뒤에도 옛 화면 호환을 위해 남겨 둔다
    return _normalize_section(payload.get("breakdown"), _construction_row, "breakdown")


def _normalize_split(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    시공 실적 / 정산 분리 (2026-09-28). 섹션마다 따로 판정한다 — 정산이 깨졌다고 시공(도넛)까지 버리지 않는다.
    split 자체가 없으면(옛 ERP) None. home.js 는 그때 monthlyRevenue 로 대신 채우지 않고 대체값 경로로 간다.

    month/from/to (2026-10-23): split 의 기간은 달력 월이 아니라 금요일 기준 주차의 달이다(ERP 공무 화면과 같은 규칙).
    home.js 는 month 로 그 달의 목표 행을 불러온다 — 실적과 목표가 같은 달을 보게. 옛 ERP 면 None(달력 월로 동작).
    """
    raw = payload.get("split")
    if not isinstance(raw, dict):
        return None
    return {
        "month": _as_month(raw.get("month")),
        "from": _as_date(raw.get("from")),
        "to": _as_date(raw.get("to")),
        "construction": _normalize_section(raw.get("construction"), _construction_row, "split.construction"),
        "settlement": _normalize_section(raw.get("settlement"), _settlement_row, "split.settlement"),
    }


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
        # 구버전 ERP(브레이크다운 배포 전)는 이 키가 없다 → None, 화면은 기존 동작 그대로
        "breakdown": _normalize_breakdown(payload),
        # 허용목록 방식이라 여기 적지 않은 칸은 브라우저에 도착하지 않는다 — split 을 추가하면 이 줄도 필요하다
        "split": _normalize_split(payload),
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
