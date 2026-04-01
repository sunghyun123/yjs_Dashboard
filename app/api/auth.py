import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.auth import SESSION_COOKIE_NAME, SESSION_TTL_DAYS, create_session, hash_password, require_session
from app.db.db_manager import DBManager


router = APIRouter(prefix="/api/auth", tags=["Auth"])
db = DBManager(db_path=settings.sqlite_db_path)


class LoginRequest(BaseModel):
    user_id: str = Field(..., description="사내 계정 ID")
    password: str = Field(..., description="비밀번호")
    register_code: str = Field(default="", description="(하위호환) 미사용")
    device_name: str = Field(default="unknown-device", description="기기 식별 이름")

class SignupRequest(BaseModel):
    user_name: str = Field(..., description="사용자 이름")
    user_id: str = Field(..., description="새 계정 ID")
    password: str = Field(..., description="비밀번호")

class FindAccountRequest(BaseModel):
    user_name: str = Field(..., description="사용자 이름")


class ResetPasswordRequest(BaseModel):
    user_name: str = Field(..., description="사용자 이름")
    user_id: str = Field(..., description="계정 ID")
    new_password: str = Field(..., description="새 비밀번호")


@router.post("/login")
def login(request: LoginRequest, response: Response):
    user = db.get_user_by_id(request.user_id)

    # DB에 admin 행이 없을 때만 INITIAL_ADMIN_PASSWORD로 최초 관리자 생성 (이관/수동 DB 삭제 대비)
    bootstrap_pw = (settings.INITIAL_ADMIN_PASSWORD or "1234").strip() or "1234"
    if not user and request.user_id == "admin" and request.password == bootstrap_pw:
        db.create_user(
            user_name="관리자",
            user_id="admin",
            password=request.password,
            role="admin",
            register_code="",
        )
        user = db.get_user_by_id(request.user_id)

    if not user:
        raise HTTPException(status_code=401, detail="계정 정보가 올바르지 않습니다.")

    hashed_input = hash_password(request.password)
    password_hash = (user.get("password_hash") or "").strip()
    password_ok = bool(password_hash and password_hash == hashed_input)
    if not password_ok:
        raise HTTPException(status_code=401, detail="계정 정보가 올바르지 않습니다.")

    session_id = create_session(db, user_id=request.user_id, device_name=request.device_name)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return {"message": "로그인 성공", "user_id": request.user_id, "role": user["role"]}


@router.post("/signup")
def signup(request: SignupRequest):
    if not settings.SIGNUP_ENABLED:
        raise HTTPException(status_code=403, detail="회원가입이 비활성화되어 있습니다.")
    try:
        db.create_user(
            user_name=request.user_name,
            user_id=request.user_id,
            password=request.password,
            role="worker",
            register_code="",
        )
        return {"status": "success", "message": "신규 사용자가 등록되었습니다."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다.")


@router.post("/find-account")
def find_account(request: FindAccountRequest):
    row = db.get_user_by_name((request.user_name or "").strip())
    if not row:
        raise HTTPException(status_code=404, detail="등록된 계정 정보가 없습니다.")
    return {
        "status": "success",
        "user_id": row["user_id"],
        "message": "비밀번호는 보안상 제공되지 않습니다. 비밀번호 재설정을 진행해 주세요.",
    }


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest):
    if len(request.new_password or "") < 4:
        raise HTTPException(status_code=400, detail="새 비밀번호는 4자 이상이어야 합니다.")
    updated = db.reset_user_password(
        user_id=request.user_id,
        user_name=request.user_name,
        new_password=request.new_password,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="일치하는 계정 정보를 찾을 수 없습니다.")
    return {"status": "success", "message": "비밀번호가 재설정되었습니다."}


@router.post("/logout")
def logout(response: Response, session=Depends(require_session)):
    db.delete_session(session["session_id"])
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=settings.COOKIE_SECURE,
    )
    return {"message": "로그아웃되었습니다."}


@router.get("/me")
def me(session=Depends(require_session)):
    return {
        "user_id": session["user_id"],
        "role": session["role"],
        "device_name": session["device_name"],
    }
