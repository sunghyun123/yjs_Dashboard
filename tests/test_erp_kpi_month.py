"""
중계 month 경로 (2026-11-10, PR-3). ERP 계약은 yjs_erp PR #52:
  ?month=YYYY-MM → 200 { month, split } / 형식·범위 오류 400 { error } / split 실패 500 { error }
중계는 month 응답을 기존 정규화(_normalize_monthly_kpi)에 넣지 않는다 — 그 함수는 updatedAt:"" 등
'이번 달' 칸을 빈 값으로 붙여 보내고, 화면이 그 빈 값을 대체값 날짜(2026-06-18)로 그린다.
"""
import httpx

from app.core.config import settings
from tests.test_smoke_basic_flow import login_as_admin

URL = "https://erp.example.test/kpi"


def _split(month="2026-10"):
    return {
        "month": month, "from": "2026-09-28", "to": "2026-11-02",
        "construction": {"rows": [{"지중no": "JG26-041", "공사명": "안양", "금액천원": 100, "일자": [1], "야간일자": []}],
                         "totalThousand": 100},
        "settlement": {"rows": [], "totalThousand": 0},
    }


def _install_fake_erp(monkeypatch, status=200, body=None, calls=None, raise_exc=None):
    import app.api.erp as erp_api

    monkeypatch.setattr(settings, "ERP_MONTHLY_KPI_URL", URL)
    monkeypatch.setattr(settings, "ERP_DASHBOARD_API_KEY", "test-token")

    class _FakeAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers, params=None):
            if calls is not None:
                calls.append(params)
            if raise_exc is not None:
                raise raise_exc
            return httpx.Response(status, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(erp_api.httpx, "AsyncClient", _FakeAsyncClient)


def test_month는_세션이_필요하다(client):
    assert client.get("/api/erp/monthly-kpi?month=2026-10").status_code == 401


def test_month를_ERP로_넘기고_month_split만_돌려준다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    calls = []
    _install_fake_erp(monkeypatch, body={"month": "2026-10", "split": _split()}, calls=calls)

    res = client.get("/api/erp/monthly-kpi?month=2026-10")

    assert res.status_code == 200
    assert calls == [{"month": "2026-10"}]
    body = res.json()
    assert set(body.keys()) == {"status", "month", "split"}
    assert body["month"] == "2026-10"
    assert body["split"]["month"] == "2026-10"
    assert body["split"]["construction"]["totalThousand"] == 100


def test_month_없으면_params를_넘기지_않는다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    calls = []
    _install_fake_erp(monkeypatch, body={"label": "11월", "split": _split("2026-11")}, calls=calls)

    res = client.get("/api/erp/monthly-kpi")

    assert res.status_code == 200
    assert calls == [None]
    assert "amounts" in res.json()


def test_month_형식이_틀리면_ERP를_부르지_않고_400(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    calls = []
    _install_fake_erp(monkeypatch, body={}, calls=calls)

    for bad in ["2026-9", "2026-13", "2026-10-01", "abc"]:
        assert client.get(f"/api/erp/monthly-kpi?month={bad}").status_code == 400
    assert calls == []


def test_ERP가_400이면_400과_ERP_문구를_그대로(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, status=400, body={"error": "month 는 2026-09~2026-11 범위"})

    res = client.get("/api/erp/monthly-kpi?month=2026-08")

    assert res.status_code == 400
    assert res.json()["detail"] == "month 는 2026-09~2026-11 범위"


def test_ERP가_500이면_503(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, status=500, body={"error": "boom"})

    assert client.get("/api/erp/monthly-kpi?month=2026-10").status_code == 503


def test_ERP가_다른_달을_돌려주면_503(client, monkeypatch, tmp_path):
    # 요청한 달과 다른 달을 그리면 '10월' 제목 아래 9월 숫자가 에러 없이 그려진다 — 계약 위반으로 본다
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, body={"month": "2026-09", "split": _split("2026-09")})

    assert client.get("/api/erp/monthly-kpi?month=2026-10").status_code == 503


def test_split이_없으면_503(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, body={"month": "2026-10", "split": None})

    assert client.get("/api/erp/monthly-kpi?month=2026-10").status_code == 503


def test_construction이_없으면_503(client, monkeypatch, tmp_path):
    # 시공 칸이 빠지면 화면은 어차피 실패를 그린다 — 200 으로 내보내지 않고 계약 위반(503)으로 본다
    login_as_admin(client, monkeypatch, tmp_path)
    split = _split()
    split["construction"] = None
    _install_fake_erp(monkeypatch, body={"month": "2026-10", "split": split})

    assert client.get("/api/erp/monthly-kpi?month=2026-10").status_code == 503


def test_옛_ERP처럼_month_키가_없으면_503(client, monkeypatch, tmp_path):
    # month 를 모르는 옛 ERP 는 이번 달 응답을 준다 — 지난 달 제목 아래 이번 달 숫자가 그려지면 안 된다
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, body={"label": "11월", "split": _split("2026-11")})

    assert client.get("/api/erp/monthly-kpi?month=2026-10").status_code == 503


def test_ERP_시간초과면_503(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, raise_exc=httpx.ConnectTimeout("t"))

    assert client.get("/api/erp/monthly-kpi?month=2026-10").status_code == 503
