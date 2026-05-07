import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.migrations import run_migrations


# Ensure required settings exist before app modules import `settings`.
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("KAKAO_REST_API_KEY", "test-kakao-key")
os.environ.setdefault("KAKAO_REDIRECT_URI", "http://testserver/api/auth/kakao/callback")
os.environ.setdefault("ALLOWED_HOSTS", "*,testserver")


def _install_google_genai_stub():
    if "google.genai" in sys.modules:
        return

    google_mod = sys.modules.get("google")
    if google_mod is None:
        google_mod = types.ModuleType("google")
        sys.modules["google"] = google_mod

    genai_mod = types.ModuleType("google.genai")
    types_mod = types.ModuleType("google.genai.types")

    class _DummyConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _DummyPart:
        @staticmethod
        def from_bytes(data, mime_type):
            return {"data": data, "mime_type": mime_type}

    class _DummyAioModels:
        async def generate_content(self, **kwargs):
            class _Resp:
                text = '{"intent":"incomplete","reply_message":"stub","target_date":null,"target_keyword":null,"schedule_data":null}'

            return _Resp()

    class _DummyClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.aio = types.SimpleNamespace(models=_DummyAioModels())

    types_mod.GenerateContentConfig = _DummyConfig
    types_mod.Part = _DummyPart
    genai_mod.Client = _DummyClient
    genai_mod.types = types_mod

    google_mod.genai = genai_mod
    sys.modules["google.genai"] = genai_mod
    sys.modules["google.genai.types"] = types_mod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    _install_google_genai_stub()

    db_path = str(tmp_path / "test_schedule.db")
    run_migrations(db_path)

    import main
    from app.db import deps
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(app_settings, "FORCE_HTTPS_REDIRECT", False)

    # Single override point: all repos resolve through get_db_path
    main.app.dependency_overrides[deps.get_db_path] = lambda: db_path

    def _discard_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(main.asyncio, "create_task", _discard_task)
    monkeypatch.chdir(Path(main.__file__).resolve().parent)

    with TestClient(main.app) as tc:
        yield tc

    main.app.dependency_overrides.clear()
