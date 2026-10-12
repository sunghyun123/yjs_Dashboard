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
        "manager": "김무선",
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


def _set_manager(client, row_id, manager):
    return client.patch(
        f"/api/admin/monthly-progress-config/target-rows/{row_id}", json={"manager": manager}
    )


def test_담당자를_바꾼다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    row = _add(client).json()["data"]["construction"][0]
    assert row["manager"] == "김무선"

    res = _set_manager(client, row["id"], "김상훈")
    assert res.status_code == 200
    updated = res.json()["data"]["construction"][0]
    assert updated["manager"] == "김상훈"
    # 담당 지정은 목표 숫자를 건드리지 않는다
    assert updated["amountThousand"] == 120000 and updated["jijungNo"] == "2026-101"

    cfg = client.get("/api/erp/monthly-progress-config?month=2026-10").json()["data"]
    assert cfg["targets"]["construction"][0]["manager"] == "김상훈"
    assert "김무선" in cfg["managers"]


def test_담당자_없이는_추가도_미지정_되돌리기도_안된다(client, monkeypatch, tmp_path):
    # 미지정 행은 홈 담당자 그래프 어디에도 속하지 못한다 — 들어오는 입구에서 막는다
    login_as_admin(client, monkeypatch, tmp_path)
    assert _add(client, manager="").status_code == 400
    assert _add(client, manager="   ").status_code == 400
    assert _add(client, manager="홍길동").status_code == 400
    body = {"month": "2026-10", "kind": "construction", "jijung_no": "X", "name": "n", "amount_thousand": 1}
    assert client.post("/api/admin/monthly-progress-config/target-rows", json=body).status_code == 422

    row = _add(client).json()["data"]["construction"][0]
    assert _set_manager(client, row["id"], "").status_code == 400


def test_담당은_그_달_그_행에만_걸린다(client, monkeypatch, tmp_path):
    # 담당이 바뀌어도 지난달 그래프가 소급해서 바뀌면 안 된다 — 같은 공사라도 달이 다르면 다른 행이다
    login_as_admin(client, monkeypatch, tmp_path)
    oct_row = _add(client, month="2026-10").json()["data"]["construction"][0]
    nov_row = _add(client, month="2026-11").json()["data"]["construction"][0]
    _set_manager(client, nov_row["id"], "이재규")

    get = lambda m: client.get(f"/api/erp/monthly-progress-config?month={m}").json()["data"]["targets"]
    assert get("2026-10")["construction"][0]["manager"] == "김무선"
    assert get("2026-11")["construction"][0]["manager"] == "이재규"


def test_담당자_지정의_잘못된_입력(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    row = _add(client).json()["data"]["construction"][0]
    assert _set_manager(client, row["id"], "홍길동").status_code == 400
    assert _set_manager(client, 99999, "김무선").status_code == 404


def test_관리자가_아니면_담당자를_못_바꾼다(client):
    assert _set_manager(client, 1, "김무선").status_code in (401, 403)


# ── 담당자 목록 ──
def test_담당자를_추가하고_지우면_목록만_바뀌고_지난_행은_남는다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    names = lambda: [m["name"] for m in client.get("/api/admin/target-managers").json()["data"]]
    assert names() == ["김무선", "김상훈", "이재규", "김단후"]  # 처음엔 기존 고정 목록으로 채워진다

    assert client.post("/api/admin/target-managers", json={"name": "박신입"}).status_code == 200
    assert client.post("/api/admin/target-managers", json={"name": "박신입"}).status_code == 409
    assert client.post("/api/admin/target-managers", json={"name": "  "}).status_code == 400
    assert _add(client, manager="박신입").status_code == 200

    new_id = next(m["id"] for m in client.get("/api/admin/target-managers").json()["data"] if m["name"] == "박신입")
    assert client.delete(f"/api/admin/target-managers/{new_id}").status_code == 200
    assert "박신입" not in names()
    # 목록에서 지워도 이미 지정된 행의 이름은 그대로다 — 지난달 그래프 보존
    targets = client.get("/api/erp/monthly-progress-config?month=2026-10").json()["data"]["targets"]
    assert targets["construction"][0]["manager"] == "박신입"
    # 지워진 사람에게 새로 지정할 수는 없다
    assert _add(client, jijung_no="NEW", manager="박신입").status_code == 400
    assert client.delete(f"/api/admin/target-managers/{new_id}").status_code == 404


# ── 계획외 공사 담당 지정 ──
def _assign(client, jijung_no, manager, month="2026-10"):
    return client.put(
        "/api/admin/monthly-progress-config/unplanned-assignments",
        json={"month": month, "jijung_no": jijung_no, "manager": manager},
    )


def test_계획외_공사를_담당자에게_지정하고_해제한다(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    assert _assign(client, "999", "김상훈").json()["data"] == [{"jijungNo": "999", "manager": "김상훈"}]
    # 같은 공사를 다시 지정하면 바뀐다(두 줄이 되지 않는다 — 두 사람에게 이중으로 붙지 않게)
    assert _assign(client, "999", "이재규").json()["data"] == [{"jijungNo": "999", "manager": "이재규"}]

    cfg = client.get("/api/erp/monthly-progress-config?month=2026-10").json()["data"]
    assert cfg["unplannedAssignments"] == [{"jijungNo": "999", "manager": "이재규"}]
    # 목표는 건드리지 않는다 — 도넛 분모가 그대로여야 한다
    assert cfg["targets"] == {"construction": [], "settlement": []}
    # 다른 달에는 안 보인다
    assert client.get("/api/erp/monthly-progress-config?month=2026-11").json()["data"]["unplannedAssignments"] == []

    assert _assign(client, "999", "").json()["data"] == []  # 해제하면 다시 계획외 실적으로


def test_계획외_지정의_잘못된_입력(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    assert _assign(client, "999", "홍길동").status_code == 400
    assert _assign(client, "  ", "김무선").status_code == 400
    assert _assign(client, "999", "김무선", month="2026-13").status_code == 400


def test_관리자가_아니면_담당자_목록과_계획외_지정을_못_바꾼다(client):
    assert client.post("/api/admin/target-managers", json={"name": "x"}).status_code in (401, 403)
    assert client.delete("/api/admin/target-managers/1").status_code in (401, 403)
    assert _assign(client, "999", "김무선").status_code in (401, 403)
