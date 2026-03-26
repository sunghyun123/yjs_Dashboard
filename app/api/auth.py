from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.core.auth import SESSION_COOKIE_NAME, SESSION_TTL_DAYS, create_session, hash_password, require_session
from app.db.db_manager import DBManager


router = APIRouter(prefix="/api/auth", tags=["Auth"])
db = DBManager(db_path="schedule.db")


class LoginRequest(BaseModel):
    user_id: str = Field(..., description="사내 계정 ID")
    password: str = Field(..., description="비밀번호")
    register_code: str = Field(..., description="등록 코드")
    device_name: str = Field(default="unknown-device", description="기기 식별 이름")


@router.post("/login")
def login(request: LoginRequest, response: Response):
    user = db.get_user_by_id(request.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="계정 정보가 올바르지 않습니다.")

    if user["password_hash"] != hash_password(request.password):
        raise HTTPException(status_code=401, detail="계정 정보가 올바르지 않습니다.")

    if user["register_code"] != request.register_code:
        raise HTTPException(status_code=403, detail="미등록 기기입니다.")

    session_id = create_session(db, user_id=request.user_id, device_name=request.device_name)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return {"message": "로그인 성공", "user_id": request.user_id, "role": user["role"]}


@router.post("/logout")
def logout(response: Response, session=Depends(require_session)):
    db.delete_session(session["session_id"])
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "로그아웃되었습니다."}


@router.get("/me")
def me(session=Depends(require_session)):
    return {
        "user_id": session["user_id"],
        "role": session["role"],
        "device_name": session["device_name"],
    }
