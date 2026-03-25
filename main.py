# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# 분리해둔 API 라우터들을 불러옵니다.
from app.api import schedules
from app.api import vision

app = FastAPI(
    title="yjs_Dashboard 현장 관리 API",
    description="현장 작업자의 비정형 텍스트 및 이미지를 분석하여 상황판에 연동합니다.",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 라우터 등록 (여기서 분리된 방들을 메인 앱에 연결해 줍니다) ---
app.include_router(schedules.router)
app.include_router(vision.router)

# --- 프론트엔드 화면 서빙 ---
@app.get("/", summary="입력창 화면", tags=["Pages"])
async def serve_index():
    return FileResponse("index.html")

@app.get("/dashboard.html", summary="상황판 화면", tags=["Pages"])
async def serve_dashboard():
    return FileResponse("dashboard.html")