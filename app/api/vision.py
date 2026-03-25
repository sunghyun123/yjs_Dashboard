import os
import pandas as pd
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.vision_ai_service import VisionService
from app.core.config import settings

router = APIRouter(prefix="/api/vision", tags=["Vision"])
vision_svc = VisionService(api_key=settings.GEMINI_API_KEY)

# 자동화 데이터가 저장될 루트 폴더
BASE_STORAGE = Path("자동화_데이터")


@router.post("/upload")
async def process_document(file: UploadFile = File(...)):
    content = await file.read()
    data = await vision_svc.analyze_document(content, file.content_type)

    if not data:
        raise HTTPException(status_code=500, detail="AI 분석 실패")

    # 1. 문서 종류별 폴더 생성
    folder = BASE_STORAGE / data['doc_type']
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

    return {"message": "분류 및 저장 완료", "folder": str(folder), "filename": safe_name}