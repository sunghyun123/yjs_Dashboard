"""
월간 목표 이미지 — 업로드·삭제·서빙.

파일을 받는 엔드포인트라 "올려서 보인다"보다 **안 되는 것**이 더 중요하다:
남이 준 파일명으로 아무 데나 쓰지 않는지, 로그인 없이 열리지 않는지,
그리고 목표금액만 고치는 저장이 이미지를 지워버리지 않는지.
"""
from pathlib import Path

from app.core.config import settings
from tests.test_smoke_basic_flow import login_as_admin

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d763f8cfc0000003010100189dd6b40000000049454e44ae426082"
)


def _upload(client, month="2026-09", content=PNG_1PX, content_type="image/png", name="목표표.png"):
    return client.post(
        f"/api/admin/monthly-progress-config/target-image?month={month}",
        files={"file": (name, content, content_type)},
    )


def _target_dir() -> Path:
    return Path(settings.UPLOADS_DIR) / "monthly-target"


def test_업로드하면_월_이름으로_저장되고_설정에_잡힌다(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    res = _upload(client)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["target_image_name"] == "2026-09.png"
    assert data["target_image_updated_at"]
    assert (_target_dir() / "2026-09.png").is_file()

    # 홈이 읽는 설정 응답에도 주소가 실려야 팝업을 그릴 수 있다
    cfg = client.get("/api/erp/monthly-progress-config?month=2026-09").json()["data"]
    assert cfg["target_image_url"] == "/uploads/monthly-target/2026-09.png"


def test_올린_사람의_파일명은_저장에_쓰이지_않는다(client, monkeypatch, tmp_path):
    # 업로드 파일명을 그대로 쓰면 이런 이름으로 상위 폴더에 쓸 수 있다.
    # 파일명은 검증된 月 + 화이트리스트 확장자로 우리가 짓는다.
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    res = _upload(client, name="../../../../evil.png")
    assert res.status_code == 200
    assert res.json()["data"]["target_image_name"] == "2026-09.png"
    assert sorted(p.name for p in _target_dir().iterdir()) == ["2026-09.png"]


def test_이상한_월은_거부한다(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    for bad in ["2026-13", "2026-9", "../2026-09", "2026-09-01", ""]:
        assert _upload(client, month=bad).status_code == 400


def test_이미지가_아니면_거부한다(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    res = _upload(client, content=b"<script>alert(1)</script>", content_type="text/html", name="x.html")
    assert res.status_code == 400
    assert not _target_dir().exists() or not any(_target_dir().iterdir())


def test_10MB를_넘으면_거부한다(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    res = _upload(client, content=b"\x00" * (10 * 1024 * 1024 + 1))
    assert res.status_code == 400


def test_확장자가_바뀌면_옛_파일을_지운다(client, monkeypatch, tmp_path):
    # png 올렸다가 jpg 로 다시 올리면 png 가 남아 아무도 안 지우는 쓰레기가 된다
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    _upload(client)
    _upload(client, content=b"\xff\xd8\xff\xdb fake jpg", content_type="image/jpeg")
    assert sorted(p.name for p in _target_dir().iterdir()) == ["2026-09.jpg"]


def test_목표금액만_저장해도_이미지는_안_지워진다(client, monkeypatch, tmp_path):
    # 사용자는 숫자만 고쳤는데 그림이 사라지면 그게 조용한 데이터 소실이다
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    _upload(client)
    res = client.put(
        "/api/admin/monthly-progress-config",
        json={"month": "2026-09", "label": "9월", "total_progress": 40.0, "target_amount_thousand": 500000},
    )
    assert res.status_code == 200
    assert res.json()["data"]["target_image_name"] == "2026-09.png"


def test_삭제하면_파일과_기록이_같이_사라진다(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    _upload(client)
    res = client.delete("/api/admin/monthly-progress-config/target-image?month=2026-09")
    assert res.status_code == 200
    assert res.json()["data"]["target_image_name"] == ""
    assert not (_target_dir() / "2026-09.png").exists()


def test_이미지는_로그인해야_열린다(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)
    _upload(client)

    assert client.get("/uploads/monthly-target/2026-09.png").status_code == 200

    client.cookies.clear()
    assert client.get("/uploads/monthly-target/2026-09.png").status_code == 401


def test_서빙_경로로_다른_파일을_꺼낼_수_없다(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    for bad in ["../../main.py", "2026-09.py", "2026-13.png", "..%2Fsecret.png"]:
        assert client.get(f"/uploads/monthly-target/{bad}").status_code in (404, 400)


def test_업로드_전에는_주소가_비어있다(client, monkeypatch, tmp_path):
    # 홈은 이 값이 비었는지로 "아직 안 올린 달"을 판단한다
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(tmp_path / "uploads"))
    login_as_admin(client, monkeypatch, tmp_path)

    cfg = client.get("/api/erp/monthly-progress-config?month=2026-12").json()["data"]
    assert cfg["target_image_name"] == ""
    assert cfg["target_image_url"] == ""
