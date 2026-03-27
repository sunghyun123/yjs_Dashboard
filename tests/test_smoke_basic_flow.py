def login_as_admin(client):
    res = client.post(
        "/api/auth/login",
        json={
            "user_id": "admin",
            "password": "1234",
            "register_code": "",
            "device_name": "pytest-device",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "로그인 성공"
    return body


def test_static_pages_are_served(client):
    page_markers = {
        "/": ["사진 카테고리 선택", "요청 접수"],
        "/dashboard.html": ["일정 수정", "오늘만"],
        "/admin.html": ["요청 반려", "전일 업로드 실행"],
        "/board.html": ["템플릿 전송 확인", "대기 중"],
    }

    for path in ["/", "/dashboard.html", "/admin.html", "/board.html"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        body = res.text
        for marker in page_markers[path]:
            assert marker in body


def test_auth_login_me_logout_flow(client):
    login_as_admin(client)

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


def test_schedule_create_and_today_read(client):
    login_as_admin(client)

    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": "2026-03-26",
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
    assert any(item["location"] == "안양" for item in today_body["data"])


def test_schedule_create_with_missing_optional_fields(client):
    login_as_admin(client)

    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": "2026-03-26",
                "location": "군포",
                "task": "야간작업",
            },
        },
    )
    assert create_res.status_code == 200
    assert create_res.json()["status"] == "success"

    today_res = client.get("/api/schedules/today")
    rows = today_res.json()["data"]
    inserted = next((row for row in rows if row["location"] == "군포" and row["task"] == "야간작업"), None)
    assert inserted is not None
    assert inserted["details"] in ["", None]
    assert inserted["category"] == "공사일정"


def test_memo_and_worker_status_flow(client):
    login_as_admin(client)

    memo_res = client.post(
        "/api/schedules/memos",
        json={"content": "현장 메모 테스트", "memo_type": "일반", "visibility": "all"},
    )
    assert memo_res.status_code == 200
    assert memo_res.json()["status"] == "success"

    memo_list_res = client.get("/api/schedules/memos")
    assert memo_list_res.status_code == 200
    memo_items = memo_list_res.json()["data"]
    assert any(item["content"] == "현장 메모 테스트" for item in memo_items)

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


def test_admin_request_queue_basic_flow(client):
    login_as_admin(client)

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


def test_execute_update_delete_go_to_admin_queue(client):
    login_as_admin(client)

    # Create a base schedule first.
    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": "2026-03-26",
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
    created = next((r for r in today_res.json()["data"] if r["location"] == "의왕" and r["task"] == "맨홀 정비"), None)
    assert created is not None
    schedule_id = created["id"]

    update_queue_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "update",
            "schedule_id": schedule_id,
            "schedule_data": {
                "date": "2026-03-26",
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


def test_admin_review_approve_update_and_delete(client):
    login_as_admin(client)

    # 1) Create original schedule.
    create_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "create",
            "schedule_data": {
                "date": "2026-03-27",
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
    base = next((r for r in base_rows if r["location"] == "안산" and r["task"] == "케이블 포설"), None)
    assert base is not None
    schedule_id = base["id"]

    # 2) Queue update request then approve it.
    queue_update_res = client.post(
        "/api/schedules/execute",
        json={
            "action": "update",
            "schedule_id": schedule_id,
            "schedule_data": {
                "date": "2026-03-27",
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
