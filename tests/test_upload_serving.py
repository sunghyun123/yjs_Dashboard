"""/uploads/photos/ 서빙 경계 — 첨부로 기록된 파일만, 로그인한 사람에게만.

2026-10-08 점검에서 로그인 없이 GET /uploads/photos/2026-07-08_백업데이터.xlsx 가 200 으로
백업 엑셀을 내준 것을 재현했다. 원인: 인증 없음 + uploads 폴더 전체를 서빙.
"""
import main
from app.db import deps
from app.db.repos.export import ExportRepository

from tests.test_smoke_basic_flow import login_as_admin


def _setup_uploads(client, monkeypatch, tmp_path, stored_path: str):
    """tmp 작업 폴더에 첨부 사진 1장 + 백업 엑셀 1개를 두고, 사진만 DB 에 첨부로 기록한다."""
    monkeypatch.chdir(tmp_path)  # UPLOADS_DIR 기본값 "uploads" 가 tmp 아래를 가리키게
    photo = tmp_path / "uploads" / "2026-10-08" / "현장사진" / "143015.jpg"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"jpeg-bytes")
    (tmp_path / "uploads" / "2026-07-08_백업데이터.xlsx").write_bytes(b"backup-bytes")

    db_path = main.app.dependency_overrides[deps.get_db_path]()
    ExportRepository(db_path).save_photo_upload(
        category="현장사진", file_path=stored_path, uploaded_by="admin",
        uploaded_device="test", related_date="2026-10-08",
    )


PHOTO_URL = "/uploads/photos/2026-10-08/현장사진/143015.jpg"


def test_anonymous_cannot_fetch_even_registered_photo(client, monkeypatch, tmp_path):
    _setup_uploads(client, monkeypatch, tmp_path, "uploads/2026-10-08/현장사진/143015.jpg")
    assert client.get(PHOTO_URL).status_code == 401


def test_logged_in_user_gets_registered_photo(client, monkeypatch, tmp_path):
    login_as_admin(client, monkeypatch, tmp_path)
    _setup_uploads(client, monkeypatch, tmp_path, "uploads/2026-10-08/현장사진/143015.jpg")
    res = client.get(PHOTO_URL)
    assert res.status_code == 200
    assert res.content == b"jpeg-bytes"


def test_windows_style_stored_path_still_matches(client, monkeypatch, tmp_path):
    # 운영 서버(윈도우)에서는 str(Path) 가 역슬래시로 저장된다
    login_as_admin(client, monkeypatch, tmp_path)
    _setup_uploads(client, monkeypatch, tmp_path, "uploads\\2026-10-08\\현장사진\\143015.jpg")
    assert client.get(PHOTO_URL).status_code == 200


def test_logged_in_user_cannot_fetch_unregistered_backup(client, monkeypatch, tmp_path):
    # 로그인만으로는 부족하다 — 파일이 디스크에 있어도 첨부 기록이 없으면 내주지 않는다
    login_as_admin(client, monkeypatch, tmp_path)
    _setup_uploads(client, monkeypatch, tmp_path, "uploads/2026-10-08/현장사진/143015.jpg")
    assert client.get("/uploads/photos/2026-07-08_백업데이터.xlsx").status_code == 404
