"""
중계 year 경로 (2026-11-13, 연간 PR-4). ERP 계약은 yjs_erp PR #58:
  ?year=YYYY → 200 { year, months: [{ month, 상태, split }] x12 }
    상태 ∈ 완료·진행중·미래, 미래 달은 split: null(약속된 빈 칸)
  형식·범위 오류 400 { error } / 계산 실패 500 { error }

중계는 허용목록이다 — 여기서 통과시키지 않은 칸(year·상태)은 브라우저에 도착하지 않는다.
미래의 null(약속)과 실패(500→503)를 섞지 않는다: 실패를 null+200 으로 감추지 않는다(11/10 결정).
"""
import copy

from tests.test_erp_kpi_month import _install_fake_erp, _split
from tests.test_smoke_basic_flow import login_as_admin


def _year_body(year="2026"):
    months = []
    for i in range(1, 13):
        m = f"{year}-{i:02d}"
        state = "완료" if i <= 10 else ("진행중" if i == 11 else "미래")
        months.append({"month": m, "상태": state, "split": None if state == "미래" else _split(m)})
    return {"year": int(year), "months": months}


def test_year는_세션이_필요하다(client):
    assert client.get("/api/erp/monthly-kpi?year=2026").status_code == 401


def test_year를_ERP로_넘기고_12달과_상태를_돌려준다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    calls = []
    _install_fake_erp(monkeypatch, body=_year_body(), calls=calls)

    res = client.get("/api/erp/monthly-kpi?year=2026")

    assert res.status_code == 200
    assert calls == [{"year": "2026"}]
    body = res.json()
    assert set(body.keys()) == {"status", "year", "months"}
    assert body["year"] == "2026"
    assert [m["month"] for m in body["months"]] == [f"2026-{i:02d}" for i in range(1, 13)]
    assert [m["상태"] for m in body["months"]] == ["완료"] * 10 + ["진행중", "미래"]
    assert body["months"][11]["split"] is None
    oct_ = body["months"][9]["split"]
    assert oct_["month"] == "2026-10"
    assert oct_["construction"]["totalThousand"] == 100
    assert oct_["settlement"] == {"rows": [], "totalThousand": 0}


def test_month와_year를_같이_주면_ERP를_부르지_않고_400(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    calls = []
    _install_fake_erp(monkeypatch, body=_year_body(), calls=calls)
    assert client.get("/api/erp/monthly-kpi?year=2026&month=2026-10").status_code == 400
    assert client.get("/api/erp/monthly-kpi?year=26").status_code == 400
    assert calls == []


def test_ERP_400은_400으로_본문을_통과시킨다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, status=400, body={"error": "year는 2026만 됩니다: '2025'"})
    res = client.get("/api/erp/monthly-kpi?year=2025")
    assert res.status_code == 400
    assert res.json()["detail"] == "year는 2026만 됩니다: '2025'"


def test_ERP_500은_503(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, status=500, body={"error": "split 실패"})
    assert client.get("/api/erp/monthly-kpi?year=2026").status_code == 503


def _broken(mutate):
    body = _year_body()
    mutate(body)
    return body


CONTRACT_BREAKS = {
    "11달": lambda b: b["months"].pop(),
    "달_순서_어긋남": lambda b: b["months"].__setitem__(slice(0, 2), [b["months"][1], b["months"][0]]),
    "연도_다름": lambda b: b.__setitem__("year", 2025),
    "상태가_셋_밖": lambda b: b["months"][3].__setitem__("상태", "마감"),
    "완료_달_split_null": lambda b: b["months"][3].__setitem__("split", None),
    "진행중_달_시공_없음": lambda b: b["months"][10]["split"].__setitem__("construction", None),
    "split_month가_원소와_다름": lambda b: b["months"][4]["split"].__setitem__("month", "2026-06"),
    "미래_달에_split": lambda b: b["months"][11].__setitem__("split", _split("2026-12")),
    "months가_리스트가_아님": lambda b: b.__setitem__("months", {}),
}


def test_계약_위반은_503(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    for name, mutate in CONTRACT_BREAKS.items():
        _install_fake_erp(monkeypatch, body=_broken(mutate))
        res = client.get("/api/erp/monthly-kpi?year=2026")
        assert res.status_code == 503, name


def test_연간_응답은_gzip으로_나간다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _install_fake_erp(monkeypatch, body=_year_body())
    res = client.get("/api/erp/monthly-kpi?year=2026", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    assert res.headers.get("content-encoding") == "gzip"
