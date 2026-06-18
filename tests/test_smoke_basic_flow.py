import io
import json
from datetime import date
from urllib.parse import parse_qs, urlparse

import app.services.kakao_oauth as kakao_oauth
from app.core.config import settings


def _iso_today() -> str:
    """기본 /today 조회 창(과거 며칠~미래 며칠) 안에 들어가도록 오늘 날짜 사용."""
    return date.today().isoformat()


def login_as_admin(client, monkeypatch, tmp_path):
    """카카오 OAuth 호출을 가짜로 두고 화이트리스트에 있는 관리자로 세션을 만든다."""
    wl = tmp_path / "kakao_whitelist.json"
    wl.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "kakao_id": "999888777",
                        "user_id": "admin",
                        "user_name": "테스트관리자",
                        "role": "admin",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "KAKAO_WHITELIST_PATH", str(wl))
    monkeypatch.setattr(kakao_oauth, "fetch_oauth_token", lambda code: {"access_token": "dummy"})
    monkeypatch.setattr(kakao_oauth, "fetch_kakao_user_id", lambda token: "999888777")

    r1 = client.get("/api/auth/kakao/login?next=/dashboard.html", follow_redirects=False)
    assert r1.status_code == 302
    loc = r1.headers.get("location") or ""
    assert "kauth.kakao.com" in loc
    qs = parse_qs(urlparse(loc).query)
    assert qs.get("state")
    state = qs["state"][0]

    r2 = client.get(f"/api/auth/kakao/callback?code=fake-code&state={state}", follow_redirects=False)
    assert r2.status_code == 302


def test_static_pages_are_served(client):
    page_markers = {
        "/": ["YJS 운영 홈", "외출/행선표"],
        "/index.html": ["사진 카테고리 선택", "요청 접수"],
        "/dashboard.html": ["일정 수정", "오늘만"],
        "/admin.html": ["요청 반려", "백업데이터 생성 실행"],
    }

    for path in ["/", "/index.html", "/dashboard.html", "/admin.html"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        body = res.text
        for marker in page_markers[path]:
            assert marker in body

    board_redirect = client.get("/board.html", follow_redirects=False)
    assert board_redirect.status_code == 307
    assert board_redirect.headers.get("location") == "/dashboard.html"


def test_auth_login_me_logout_flow(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    me = me_res.json()
    assert me["user_id"] == "admin"
    assert me["role"] == "admin"

    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["message"] == "로그아웃되었습니다."

    unauthorized_me = client.get("/api/auth/me")
    assert unauthorized_me.status_code == 401


def test_erp_monthly_kpi_proxy_requires_session(client):
    res = client.get("/api/erp/monthly-kpi")
    assert res.status_code == 401


def test_erp_monthly_kpi_proxy_returns_normalized_payload(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    import app.api.erp as erp_api

    monkeypatch.setattr(settings, "ERP_MONTHLY_KPI_URL", "https://erp.example.test/kpi")
    monkeypatch.setattr(settings, "ERP_DASHBOARD_API_KEY", "test-token")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "label": "6월",
                "amounts": {
                    "monthlyRevenue": 123456000,
                    "monthlyInput": 100000000,
                    "monthlyProfit": 23456000,
                },
                "formatted": {
                    "monthlyRevenue": "123,456,000원",
                    "monthlyInput": "100,000,000원",
                    "monthlyProfit": "23,456,000원",
                },
                "updatedAt": "2026-06-18T12:34:56+09:00",
            }

    class _FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers):
            assert url == "https://erp.example.test/kpi"
            assert headers["Authorization"] == "Bearer test-token"
            return _FakeResponse()

    monkeypatch.setattr(erp_api.httpx, "AsyncClient", _FakeAsyncClient)

    res = client.get("/api/erp/monthly-kpi")
    assert res.status_code == 200
    body = res.json()
    assert body["label"] == "6월"
    assert body["amounts"]["monthlyRevenue"] == 123456000
    assert body["formatted"]["monthlyRevenue"] == "123,456,000원"
    assert body["updatedAt"] == "2026-06-18T12:34:56+09:00"


def test_monthly_progress_config_admin_save_and_home_read(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    save_res = client.put(
        "/api/admin/monthly-progress-config",
        json={
            "month": "2026-07",
            "label": "7월",
            "total_progress": 12.3,
            "target_amount_thousand": 555000,
        },
    )
    assert save_res.status_code == 200
    saved = save_res.json()["data"]
    assert saved["month"] == "2026-07"
    assert saved["label"] == "7월"
    assert saved["total_progress"] == 12.3
    assert saved["target_amount_thousand"] == 555000

    home_res = client.get("/api/erp/monthly-progress-config?month=2026-07")
    assert home_res.status_code == 200
    cfg = home_res.json()["data"]
    assert cfg["label"] == "7월"
    assert cfg["target_amount_thousand"] == 555000


def test_kakao_login_pending_then_admin_approve_flow(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    monkeypatch.setattr(kakao_oauth, "fetch_kakao_user_id", lambda token: "111222333")
    login_res = client.get("/api/auth/kakao/login?next=/dashboard.html", follow_redirects=False)
    assert login_res.status_code == 302
    state = parse_qs(urlparse(login_res.headers.get("location") or "").query)["state"][0]
    callback_res = client.get(f"/api/auth/kakao/callback?code=fake-code&state={state}", follow_redirects=False)
    assert callback_res.status_code == 302
    assert "kakao_denied=pending" in (callback_res.headers.get("location") or "")

    pending_res = client.get("/api/admin/login-access-requests?status=pending")
    assert pending_res.status_code == 200
    pending_rows = pending_res.json().get("data") or []
    target = next((row for row in pending_rows if row.get("kakao_id") == "111222333"), None)
    assert target is not None

    approve_res = client.post(
        f"/api/admin/login-access-requests/{target['id']}/review",
        json={"decision": "approve", "role": "worker", "note": "테스트 승인"},
    )
    assert approve_res.status_code == 200
    assert approve_res.json().get("status") == "success"

    login_res2 = client.get("/api/auth/kakao/login?next=/dashboard.html", follow_redirects=False)
    assert login_res2.status_code == 302
    state2 = parse_qs(urlparse(login_res2.headers.get("location") or "").query)["state"][0]
    callback_res2 = client.get(f"/api/auth/kakao/callback?code=fake-code&state={state2}", follow_redirects=False)
    assert callback_res2.status_code == 302
    assert callback_res2.headers.get("location") == "/dashboard.html"

    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    me = me_res.json()
    assert me.get("user_id") == "kakao_111222333"
    assert me.get("role") == "worker"


def test_schedule_create_and_today_read(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    d = _iso_today()

    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": d,
                "location": "안양",
                "task": "지중화 공사",
                "person": "김대리",
                "details": "기본 동작 테스트",
                "tags": ["주간"],
                "category": "공사일정",
            },
        },
    )
    assert create_res.status_code == 200
    create_body = create_res.json()
    assert create_body["status"] == "success"

    today_res = client.get("/api/schedules/today")
    assert today_res.status_code == 200
    today_body = today_res.json()
    assert today_body["count"] >= 1
    created = next((item for item in today_body["data"] if item["task"] == "지중화 공사"), None)
    assert created is not None
    assert created.get("shift_type") == "주간"


def test_schedule_create_with_missing_optional_fields(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    d = _iso_today()

    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": d,
                "location": "군포",
                "task": "야간작업",
            },
        },
    )
    assert create_res.status_code == 200
    assert create_res.json()["status"] == "success"

    today_res = client.get("/api/schedules/today")
    rows = today_res.json()["data"]
    inserted = next((row for row in rows if row["task"] == "야간작업"), None)
    assert inserted is not None
    assert inserted["details"] in ["", None]
    assert inserted["category"] == "공사 일정"


def test_import_construction_plan_creates_photo_plan_rows(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    d = _iso_today()
    imp = client.post(
        "/api/schedules/import-construction-plan",
        json={
            "date": d,
            "rows": [
                {
                    "team": "공사1팀",
                    "task": "자동추출 스모크 공사",
                    "work_code": "SY26-005",
                    "workers": "김,이",
                    "details": "상세 본문",
                    "equipment": "1번 크레인",
                    "shift_note": "야간",
                }
            ],
        },
    )
    assert imp.status_code == 200
    body = imp.json()
    assert body.get("count") == 1
    assert isinstance(body.get("inserted_ids"), list)
    day = client.get(f"/api/schedules/today?date={d}")
    assert day.status_code == 200
    rows = day.json().get("data") or []
    found = [x for x in rows if "자동추출 스모크 공사" in str(x.get("task", ""))]
    assert len(found) == 1
    assert found[0].get("source_kind") == "photo_plan"
    assert found[0].get("work_code") == "SY26-005"
    assert int(found[0].get("photo_plan_acknowledged") or 0) == 0

    ack = client.post(
        "/api/schedules/acknowledge-photo-plan",
        json={"schedule_id": found[0]["id"]},
    )
    assert ack.status_code == 200
    day2 = client.get(f"/api/schedules/today?date={d}")
    row2 = next((x for x in (day2.json().get("data") or []) if x.get("id") == found[0]["id"]), None)
    assert row2 and int(row2.get("photo_plan_acknowledged") or 0) == 1


def test_import_construction_plan_invalid_date(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    bad = client.post(
        "/api/schedules/import-construction-plan",
        json={"date": "not-a-date", "rows": [{"task": "x", "team": "", "workers": ""}]},
    )
    assert bad.status_code == 400


def test_worker_status_flow(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    status_set_res = client.post(
        "/api/schedules/worker-status",
        json={
            "user_name": "홍길동",
            "status": "외출",
            "location": "현장 A",
            "until_time": "",
            "note": "장비 점검",
        },
    )
    assert status_set_res.status_code == 200
    assert status_set_res.json()["status"] == "success"

    status_get_res = client.get("/api/schedules/worker-status")
    assert status_get_res.status_code == 200
    statuses = status_get_res.json()["data"]
    assert any(item["user_name"] == "홍길동" and item["status"] == "외출" for item in statuses)

    vacation_set_res = client.post(
        "/api/schedules/worker-status",
        json={
            "user_name": "홍길동",
            "status": "휴가",
            "location": "",
            "until_time": "",
            "note": "연차",
        },
    )
    assert vacation_set_res.status_code == 200
    assert vacation_set_res.json()["status"] == "success"

    status_get_res2 = client.get("/api/schedules/worker-status")
    assert status_get_res2.status_code == 200
    statuses2 = status_get_res2.json()["data"]
    assert any(item["user_name"] == "홍길동" and item["status"] == "휴가" for item in statuses2)


def test_admin_request_queue_basic_flow(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)

    chat_res = client.post(
        "/api/schedules/chat",
        json={"text": "삭제 요청 테스트", "input_category": "delete_request"},
    )
    assert chat_res.status_code == 200
    chat_body = chat_res.json()
    assert chat_body["intent"] == "incomplete"
    assert "관리자" in chat_body["reply_message"]

    req_res = client.get("/api/admin/requests")
    assert req_res.status_code == 200
    requests = req_res.json()["data"]
    assert len(requests) >= 1
    assert any(row["request_type"] == "delete_request" for row in requests)


def test_execute_update_delete_go_to_admin_queue(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    d = _iso_today()

    # Create a base schedule first.
    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": d,
                "location": "의왕",
                "task": "맨홀 정비",
                "person": "박대리",
                "details": "큐 테스트용 생성",
                "tags": ["주간"],
                "category": "공사일정",
            },
        },
    )
    assert create_res.status_code == 200
    assert create_res.json()["status"] == "success"

    today_res = client.get("/api/schedules/today")
    assert today_res.status_code == 200
    created = next((r for r in today_res.json()["data"] if r["task"] == "맨홀 정비"), None)
    assert created is not None
    schedule_id = created["id"]

    update_queue_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "update",
            "schedule_id": schedule_id,
            "schedule_data": {
                "date": d,
                "location": "의왕",
                "task": "맨홀 정비(수정요청)",
                "person": "박대리",
                "details": "관리자 승인 필요",
                "tags": ["주간"],
                "category": "공사일정",
            },
        },
    )
    assert update_queue_res.status_code == 200
    assert update_queue_res.json()["status"] == "success"
    assert "관리자 승인 요청" in update_queue_res.json()["message"]

    delete_queue_res = client.post(
        "/api/schedules/execute",
        json={"action": "delete", "schedule_id": schedule_id},
    )
    assert delete_queue_res.status_code == 200
    assert delete_queue_res.json()["status"] == "success"
    assert "관리자 승인 요청" in delete_queue_res.json()["message"]

    admin_req_res = client.get("/api/admin/requests")
    assert admin_req_res.status_code == 200
    rows = admin_req_res.json()["data"]
    assert any(row["request_type"] == "update_request" for row in rows)
    assert any(row["request_type"] == "delete_request" for row in rows)


def test_admin_review_approve_update_and_delete(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    d = _iso_today()

    # 1) Create original schedule.
    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": d,
                "location": "안산",
                "task": "케이블 포설",
                "person": "이대리",
                "details": "원본",
                "tags": ["야간"],
                "category": "공사일정",
            },
        },
    )
    assert create_res.status_code == 200

    base_rows = client.get("/api/schedules/today").json()["data"]
    base = next((r for r in base_rows if r["task"] == "케이블 포설"), None)
    assert base is not None
    schedule_id = base["id"]

    # 2) Queue update request then approve it.
    queue_update_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "update",
            "schedule_id": schedule_id,
            "schedule_data": {
                "date": d,
                "location": "안산",
                "task": "케이블 포설(승인수정)",
                "person": "이대리",
                "details": "관리자 승인 반영",
                "tags": ["야간", "긴급"],
                "category": "공사일정",
            },
        },
    )
    assert queue_update_res.status_code == 200

    req_rows = client.get("/api/admin/requests").json()["data"]
    update_req = next((r for r in req_rows if r["request_type"] == "update_request"), None)
    assert update_req is not None

    approve_update_res = client.post(
        "/api/admin/requests/review",
        json={"request_id": update_req["id"], "decision": "approve", "schedule_id": schedule_id},
    )
    assert approve_update_res.status_code == 200

    updated_rows = client.get("/api/schedules/today").json()["data"]
    updated = next((r for r in updated_rows if r["id"] == schedule_id), None)
    assert updated is not None
    assert updated["task"] == "케이블 포설(승인수정)"

    # 3) Queue delete request then approve it.
    queue_delete_res = client.post(
        "/api/schedules/execute",
        json={"action": "delete", "schedule_id": schedule_id},
    )
    assert queue_delete_res.status_code == 200

    req_rows_after = client.get("/api/admin/requests").json()["data"]
    delete_req = next((r for r in req_rows_after if r["request_type"] == "delete_request"), None)
    assert delete_req is not None

    approve_delete_res = client.post(
        "/api/admin/requests/review",
        json={
            "request_id": delete_req["id"],
            "decision": "approve",
            "schedule_id": schedule_id,
            "reason": "삭제 스모크 테스트",
        },
    )
    assert approve_delete_res.status_code == 200

    final_rows = client.get("/api/schedules/today").json()["data"]
    assert all(r["id"] != schedule_id for r in final_rows)


def test_direct_update_delete_require_auth(client):
    update_res = client.post(
        "/api/schedules/direct-update",
        json={"schedule_id": 1, "schedule_data": {"date": "2026-03-30", "location": "의정부", "task": "점검"}},
    )
    assert update_res.status_code == 401

    delete_res = client.post("/api/schedules/direct-delete", json={"schedule_id": 1})
    assert delete_res.status_code == 401


def test_pwa_manifest_served(client):
    res = client.get("/site.webmanifest")
    assert res.status_code == 200
    data = res.json()
    assert data.get("display") == "standalone"
    assert "start_url" in data
