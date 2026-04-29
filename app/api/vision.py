import os
import pandas as pd
from pathlib import Path
from datetime import datetime
import hashlib
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from app.services.vision_ai_service import VisionService
from app.core.config import settings
from app.db.db_manager import DBManager
from app.core.auth import require_session

router = APIRouter(prefix="/api/vision", tags=["Vision"])
vision_svc = VisionService(api_key=settings.GEMINI_API_KEY)
db = DBManager(db_path=settings.sqlite_db_path)

# 자동화 데이터가 저장될 루트 폴더
BASE_STORAGE = Path("자동화_데이터")


def _to_worklog_records(extracted: dict) -> list[dict]:
    work_code = str(extracted.get("project_code") or "").strip()
    input_date = str(extracted.get("work_date") or "").strip()
    regular_count = int(extracted.get("regular_count") or 0)
    daily_count = int(extracted.get("daily_count") or 0)
    signalman_count = int(extracted.get("signalman_count") or 0)
    excavator_6w = int(extracted.get("excavator_6w") or 0)
    excavator_3w = int(extracted.get("excavator_3w") or 0)
    dump_15t = int(extracted.get("dump_15t") or 0)
    crane_count = int(extracted.get("crane_count") or 0)

    is_night = bool(extracted.get("is_night"))

    def make_row(item_name: str, value: int) -> dict:
        value = int(value or 0)
        return {
            "work_code": work_code,
            "input_date": input_date,
            "item_name": item_name,
            "day_value": 0 if is_night else value,
            "night_value": value if is_night else 0,
        }

    return [
        make_row("상용직", regular_count),
        make_row("일용직", daily_count),
        make_row("모범신호수", signalman_count),
        make_row("6W", excavator_6w),
        make_row("3W", excavator_3w),
        make_row("덤프15T", dump_15t),
        make_row("크레인", crane_count),
    ]


@router.post("/extract-worklog")
async def extract_worklog(
    file: UploadFile = File(...),
    _user_session=Depends(require_session),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")

    data = await vision_svc.analyze_document(content, file.content_type or "image/jpeg")
    if not data:
        raise HTTPException(status_code=500, detail="AI 분석 실패")

    records = _to_worklog_records(data)
    return {
        "message": "추출 완료",
        "source": "ai",
        "raw": data,
        "records": records,
    }


@router.post("/upload")
async def process_document(
    file: UploadFile = File(...),
    upload_category: str = Form(default=""),
    user_session=Depends(require_session),
):
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    file_size = len(content)

    # 사용자 지정 카테고리 업로드 (모바일/PC 사진 전송)
    if upload_category:
        date_dir = datetime.now().strftime("%Y-%m-%d")
        folder = BASE_STORAGE / date_dir / upload_category
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = datetime.now().strftime("%H%M%S")
        save_path = folder / f"{safe_name}{Path(file.filename).suffix}"
        with open(save_path, "wb") as f:
            f.write(content)
        db.save_photo_upload(
            category=upload_category,
            file_path=str(save_path),
            uploaded_by=user_session["user_id"],
            uploaded_device=user_session.get("device_name", "unknown-device"),
            related_date=date_dir,
            file_size=file_size,
            file_sha256=file_hash,
        )
        return {"message": "사진 저장 완료", "folder": str(folder), "filename": save_path.name}

    data = await vision_svc.analyze_document(content, file.content_type)

    if not data:
        raise HTTPException(status_code=500, detail="AI 분석 실패")

    # 1. 문서 종류별 폴더 생성
    date_dir = datetime.now().strftime("%Y-%m-%d")
    folder = BASE_STORAGE / date_dir / data['doc_type']
    folder.mkdir(parents=True, exist_ok=True)

    # 2. 파일명 조합 (YYYY-MM-DD_공사명_코드)
    safe_name = f"{data['work_date']}_{data['project_name']}_{data['project_code']}".replace("/", "-")

    # 3. 엑셀 파일 저장 (ERP 양식)
    if data['doc_type'] == "작업일지":
        df = pd.DataFrame([{
            "투입일": data['work_date'], "지중No": data['project_code'], "공사명": data['project_name'],
            "주야": "야간" if data['is_night'] else "주간",
            "상용직": data['regular_count'], "일용직": data['daily_count'], "신호수": data['signalman_count'],
            "6W": data['excavator_6w'], "3W": data['excavator_3w'], "15T": data['dump_15t'], "크레인": data['crane_count']
        }])
        df.to_excel(folder / f"{safe_name}.xlsx", index=False)

    # 4. 원본 사진 저장 (검수용)
    with open(folder / f"{safe_name}{Path(file.filename).suffix}", "wb") as f:
        f.write(content)

    db.save_photo_upload(
        category=data['doc_type'],
        file_path=str(folder / f"{safe_name}{Path(file.filename).suffix}"),
        uploaded_by=user_session["user_id"],
        uploaded_device=user_session.get("device_name", "unknown-device"),
        related_date=date_dir,
        file_size=file_size,
        file_sha256=file_hash,
    )

    return {"message": "분류 및 저장 완료", "folder": str(folder), "filename": safe_name}