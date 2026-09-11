"""
총 공정률 도넛의 '실적 상세' — ERP 응답 재포장 규칙.

이 기능의 존재 이유가 "표의 합계 == 도넛의 실적"이라, 재포장이 행을 한 줄이라도 흘리면
표는 조용히 틀린 표가 된다. 그래서 여기 테스트는 대부분 "이상하면 상세를 통째로 버린다"를 확인한다.
"""
from app.api.erp import _normalize_monthly_kpi


def _payload(breakdown=None):
    body = {
        "label": "9월",
        "amounts": {"monthlyRevenue": 149_318_400},
        "formatted": {"monthlyRevenue": "1.49억"},
        "updatedAt": "2026-09-11T05:20:00Z",
    }
    if breakdown is not None:
        body["breakdown"] = breakdown
    return body


def _row(no="2026-041", name="안양 평촌대로 지중화", amount=32450, days=None, nights=None):
    return {
        "지중no": no,
        "공사명": name,
        "금액천원": amount,
        "일자": days if days is not None else [1, 2, 3],
        "야간일자": nights if nights is not None else [2],
    }


def test_정상_응답은_행과_합계를_그대로_넘긴다():
    out = _normalize_monthly_kpi(_payload({
        "rows": [_row(), _row(no="2026-018", name="군포 산본로", amount=-1182, days=[], nights=[])],
        "totalThousand": 31268,
    }))["breakdown"]

    assert [r["jijungNo"] for r in out["rows"]] == ["2026-041", "2026-018"]
    assert out["rows"][0]["days"] == [1, 2, 3]
    assert out["rows"][0]["nightDays"] == [2]
    assert out["totalThousand"] == 31268


def test_합계는_행을_직접_더해서_만든다():
    # ERP가 총액을 안 보내도 화면에 보이는 행의 합으로 채운다
    out = _normalize_monthly_kpi(_payload({
        "rows": [_row(amount=1000), _row(no="2026-018", amount=-300)],
    }))["breakdown"]
    assert out["totalThousand"] == 700


def test_ERP가_말한_합계와_행의_합이_다르면_상세를_버린다():
    # 모자란 표를 보여주느니 없는 게 낫다 — 합계가 도넛과 어긋나는 순간 표는 신뢰를 잃는다
    out = _normalize_monthly_kpi(_payload({
        "rows": [_row(amount=100)],
        "totalThousand": 999,
    }))["breakdown"]
    assert out is None


def test_깨진_행이_섞이면_상세를_버린다():
    out = _normalize_monthly_kpi(_payload({
        "rows": [_row(amount=100), "이건 객체가 아님"],
        "totalThousand": 100,
    }))["breakdown"]
    assert out is None


def test_breakdown이_없는_구버전_ERP는_None():
    # 브레이크다운 배포 전 ERP에 붙어도 도넛은 기존 경로로 그대로 그려져야 한다
    assert _normalize_monthly_kpi(_payload())["breakdown"] is None


def test_행이_하나도_없는_달은_None이_아니라_빈_목록이다():
    # "이번 달 실적 0건"과 "상세를 못 불러옴"은 다른 상황이다.
    # 여기서 None으로 뭉개면 화면이 멀쩡한 달을 고장이라고 말하게 된다.
    out = _normalize_monthly_kpi(_payload({"rows": [], "totalThousand": 0}))["breakdown"]
    assert out == {"rows": [], "totalThousand": 0}


def test_일자는_1에서_31_사이_정수만_남긴다():
    out = _normalize_monthly_kpi(_payload({
        "rows": [_row(amount=100, days=[1, "5", 0, 32, None, "뭐야"], nights=None)],
        "totalThousand": 100,
    }))["breakdown"]
    assert out["rows"][0]["days"] == [1, 5]


def test_야간일자가_배열이_아니면_빈_배열로_본다():
    out = _normalize_monthly_kpi(_payload({
        "rows": [_row(amount=100, nights="야간")],
        "totalThousand": 100,
    }))["breakdown"]
    assert out["rows"][0]["nightDays"] == []


def test_금액이_문자열로_와도_정수로_강제한다():
    out = _normalize_monthly_kpi(_payload({
        "rows": [_row(amount="32450.4")],
        "totalThousand": 32450,
    }))["breakdown"]
    assert out["rows"][0]["amountThousand"] == 32450
