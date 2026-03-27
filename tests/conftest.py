import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.db_manager import DBManager


# Ensure required settings exist before app modules import `settings`.
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "admin1234")
os.environ.setdefault("INITIAL_REGISTER_CODE", "YJS-REGISTER-001")


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
    # Use a dedicated temporary DB for each test.
    db_path = str(tmp_path / "test_schedule.db")
    test_db = DBManager(db_path=db_path)

    # Delay imports so env vars above are already set.
    import main
    from app.api import admin, auth, schedules, vision
    from app.core import auth as auth_core

    # Replace module-level DB singletons to avoid touching real `schedule.db`.
    schedules.db = test_db
    auth.db = test_db
    admin.db = test_db
    admin.export_svc.db = test_db
    vision.db = test_db

    # Force auth dependency to query the temporary DB.
    monkeypatch.setattr(auth_core, "DBManager", lambda db_path="schedule.db": test_db)

    # Avoid starting the infinite background export loop during tests.
    def _discard_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(main.asyncio, "create_task", _discard_task)

    # Ensure static files resolve from repository root.
    monkeypatch.chdir(Path(main.__file__).resolve().parent)

    with TestClient(main.app) as tc:
        yield tc
