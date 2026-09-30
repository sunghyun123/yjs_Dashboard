"""
월간 목표 행 — 시공 목표 / 정산 목표.

목표 총액은 저장하지 않고 행의 합으로만 만든다. 그래서 여기서 지킬 것은
"행이 정확히 들어가고 나간다"와 "같은 공사가 두 번 들어가 목표가 부풀지 않는다"이다.
"""
from tests.test_smoke_basic_flow import login_as_admin


def _add(client, **overrides):
    body = {
        "month": "2026-10",
        "kind": "construction",
        "jijung_no": "2026-101",
        "name": "안양 지중화 1공구",
        "amount_thousand": 120000,
    }
    body.update(overrides)
    return client.post("/api/admin/monthly-progress-config/target-rows", json=body)


def test_추가한_행이_종류별로_홈_설정에_실린다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    assert _add(client).status_code == 200
    assert _add(client, kind="settlement", amount_thousand=80000).status_code == 200

    # 홈은 로그인만 된 사람도 읽는 경로(/api/erp)로 목표를 받는다
    targets = client.get("/api/erp/monthly-progress-config?month=2026-10").json()["data"]["targets"]
    assert [r["amountThousand"] for r in targets["construction"]] == [120000]
    assert [r["amountThousand"] for r in targets["settlement"]] == [80000]
    assert targets["construction"][0]["jijungNo"] == "2026-101"


def test_같은_달_같은_종류에_같은_지중No는_거부한다(client, monkeypatch, tmp_path):
    # 두 번 들어가면 도넛 분모가 조용히 부푼다 — 화면으로는 알아챌 방법이 없다
    login_as_admin(client, monkeypatch, tmp_path)

    assert _add(client).status_code == 200
    assert _add(client, amount_thousand=999).status_code == 409
    # 종류가 다르거나 달이 다르면 같은 공사도 들어갈 수 있다
    assert _add(client, kind="settlement").status_code == 200
    assert _add(client, month="2026-11").status_code == 200


def test_달이_다르면_목표가_섞이지_않는다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _add(client, month="2026-10")

    targets = client.get("/api/erp/monthly-progress-config?month=2026-11").json()["data"]["targets"]
    assert targets == {"construction": [], "settlement": []}


def test_삭제하면_그_행만_빠진다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _add(client, jijung_no="A")
    rows = _add(client, jijung_no="B").json()["data"]["construction"]
    first_id = rows[0]["id"]

    res = client.delete(f"/api/admin/monthly-progress-config/target-rows/{first_id}")
    assert res.status_code == 200
    assert [r["jijungNo"] for r in res.json()["data"]["construction"]] == ["B"]
    assert client.delete(f"/api/admin/monthly-progress-config/target-rows/{first_id}").status_code == 404


def test_잘못된_입력은_거부한다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    assert _add(client, month="2026-13").status_code == 400
    assert _add(client, kind="plan").status_code == 422
    assert _add(client, jijung_no="   ").status_code == 400
    assert _add(client, amount_thousand=0).status_code == 422
    assert _add(client, amount_thousand=-5).status_code == 422


def test_관리자가_아니면_추가도_삭제도_못한다(client):
    assert _add(client).status_code in (401, 403)
    assert client.delete("/api/admin/monthly-progress-config/target-rows/1").status_code in (401, 403)


def test_설정_저장이_목표_행을_지우지_않는다(client, monkeypatch, tmp_path):
    # 폼 저장은 전체 덮어쓰기다 — 라벨·공정률 저장이 같은 달의 목표 행을 건드리면 안 된다
    login_as_admin(client, monkeypatch, tmp_path)
    _add(client)

    res = client.put(
        "/api/admin/monthly-progress-config",
        json={"month": "2026-10", "label": "10월", "total_progress": 12.5},
    )
    assert res.status_code == 200
    assert len(res.json()["data"]["targets"]["construction"]) == 1
