import logging
import subprocess
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import require_session
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local", tags=["LocalApps"])


class LaunchRequest(BaseModel):
    app: Literal["hangul", "erp"] = Field(..., description="hangul=한글 생성기, erp=ERP")


def _safe_resolve_under_root(root: Path, name: str) -> Path:
    if not name or name.strip() != name:
        raise ValueError("잘못된 실행 파일 이름입니다.")
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError("경로 탐색 문자는 사용할 수 없습니다.")
    p = (root / name).resolve()
    if not str(p).startswith(str(root.resolve())):
        raise ValueError("실행 파일이 허용된 폴더 밖입니다.")
    return p


@router.post("/launch", summary="로컬 PC에서 등록된 exe 실행(서버와 동일 PC일 때만)")
def launch_local_app(body: LaunchRequest, _session=Depends(require_session)):
    root_raw = (settings.LOCAL_APPS_ROOT or "").strip()
    if not root_raw:
        raise HTTPException(
            status_code=503,
            detail="로컬 앱 실행이 비활성화되어 있습니다. 서버 .env에 LOCAL_APPS_ROOT 를 설정하세요.",
        )
    root = Path(root_raw).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=503, detail="LOCAL_APPS_ROOT 폴더를 찾을 수 없습니다.")

    exe_name = settings.LOCAL_APP_HANGUL if body.app == "hangul" else settings.LOCAL_APP_ERP
    try:
        exe_path = _safe_resolve_under_root(root, exe_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not exe_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"실행 파일이 없습니다: {exe_path.name} (LOCAL_APPS_ROOT={root})",
        )

    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
    except Exception as e:
        logger.exception("로컬 앱 실행 실패")
        raise HTTPException(status_code=500, detail=f"실행에 실패했습니다: {e}") from e

    return {"message": "실행 요청을 보냈습니다.", "app": body.app, "path": exe_path.name}
