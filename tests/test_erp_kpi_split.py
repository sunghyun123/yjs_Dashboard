"""
대시보드 실적 분리(split) — ERP 응답 재포장 규칙 (2026-09-28).

split.construction 은 도넛의 분자, split.settlement 는 캡션의 정산 줄이다.
둘 다 "표의 합계 == 화면의 숫자"라, 행이 하나라도 새면 그 섹션만 통째로 버린다(None).
split 이 없으면(옛 ERP) None — 화면은 monthlyRevenue 로 대신 채우지 않는다(home.js).
"""
from app.api.erp import _normalize_monthly_kpi


def _payload(split=None):
    body = {
        "label": "9월",
        "amounts": {"monthlyRevenue": 293_816_000},
        "formatted": {"monthlyRevenue": "2.94억"},
        "updatedAt": "2026-09-28T03:00:00Z",
    }
    if split is not None:
        body["split"] = split
    return body


def _c_row(no="JG26-041", amount=32450, days=None, nights=None):
    return {
        "지중no": no,
        "공사명": "안양 평촌대로 지중화",
        "금액천원": amount,
        "일자": days if days is not None else [1, 2],
        "야간일자": nights if nights is not None else [2],
    }


def _s_row(no="JG26-018", kind="기성 2차", day=23, amount=30000):
    return {"지중no": no, "공사명": "군포 산본로", "구분": kind, "일": day, "금액천원": amount}


def test_split이_없으면_None():
    assert _normalize_monthly_kpi(_payload())["split"] is None


def test_split이_객체가_아니면_None():
    assert _normalize_monthly_kpi(_payload(split=[1, 2]))["split"] is None


def test_정상_응답은_두_섹션을_영문_키로_넘긴다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row()], "totalThousand": 32450},
        "settlement": {"rows": [_s_row(), _s_row(no="JG26-020", kind="준공", day=10, amount=-1182)],
                       "totalThousand": 28818},
    }))["split"]

    c = out["construction"]
    assert c["rows"][0] == {
        "jijungNo": "JG26-041", "name": "안양 평촌대로 지중화",
        "amountThousand": 32450, "days": [1, 2], "nightDays": [2],
    }
    assert c["totalThousand"] == 32450

    s = out["settlement"]
    assert s["rows"][0] == {
        "jijungNo": "JG26-018", "name": "군포 산본로", "kind": "기성 2차", "day": 23, "amountThousand": 30000,
    }
    assert s["rows"][1]["amountThousand"] == -1182
    assert s["totalThousand"] == 28818


def test_construction_합계가_어긋나면_construction만_버리고_settlement는_유지():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row(amount=100)], "totalThousand": 999},
        "settlement": {"rows": [_s_row(amount=500)], "totalThousand": 500},
    }))["split"]
    assert out["construction"] is None
    assert out["settlement"]["totalThousand"] == 500


def test_settlement_행이_하나라도_안_읽히면_settlement만_버린다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row(amount=100)], "totalThousand": 100},
        "settlement": {"rows": [_s_row(), "깨진 행"], "totalThousand": 30000},
    }))["split"]
    assert out["construction"]["totalThousand"] == 100
    assert out["settlement"] is None


def test_정산_일이_1에서_31_밖이면_None으로_둔다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [], "totalThousand": 0},
        "settlement": {"rows": [_s_row(day=45), _s_row(day="<b>")], "totalThousand": 60000},
    }))["split"]
    assert [r["day"] for r in out["settlement"]["rows"]] == [None, None]


def test_숫자가_문자열로_와도_정수로_강제한다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row(amount="1200")], "totalThousand": "1200"},
        "settlement": {"rows": [], "totalThousand": 0},
    }))["split"]
    assert out["construction"]["rows"][0]["amountThousand"] == 1200
    assert out["settlement"]["rows"] == []


def test_기존_breakdown_칸은_split과_무관하게_그대로():
    body = _payload({"construction": {"rows": [], "totalThousand": 0}, "settlement": {"rows": [], "totalThousand": 0}})
    body["breakdown"] = {"rows": [_c_row(amount=700)], "totalThousand": 700}
    out = _normalize_monthly_kpi(body)
    assert out["breakdown"]["totalThousand"] == 700
    assert out["amounts"]["monthlyRevenue"] == 293_816_000
