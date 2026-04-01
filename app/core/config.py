# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Schedule API"
    GEMINI_API_KEY: str
    DATABASE_URL: str
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: str = "*"
    ALLOWED_HOSTS: str = "*"
    # 빈 DB 최초 기본 관리자(admin) 비밀번호. 배포 시 .env에서 반드시 강한 값으로 변경.
    INITIAL_ADMIN_PASSWORD: str = "1234"
    # 공개 배포 시 false 권장 (무인 가입 차단)
    SIGNUP_ENABLED: bool = True
    # HTTPS 리버스 프록시 뒤에서 true (쿠키 Secure)
    COOKIE_SECURE: bool = False

    model_config = SettingsConfigDict(env_file=".env")  # .env 파일을 읽어오도록 설정

    @property
    def cors_origin_list(self) -> list[str]:
        values = [v.strip() for v in self.ALLOWED_ORIGINS.split(",") if v.strip()]
        return values or ["*"]

    @property
    def trusted_host_list(self) -> list[str]:
        values = [v.strip() for v in self.ALLOWED_HOSTS.split(",") if v.strip()]
        return values or ["*"]

    @property
    def sqlite_db_path(self) -> str:
        """
        DATABASE_URL 값을 SQLite 파일 경로로 변환한다.
        - sqlite:///schedule.db -> schedule.db
        - sqlite:////abs/path.db -> /abs/path.db
        그 외 값은 안전하게 기본값 schedule.db로 되돌린다.
        """
        raw = (self.DATABASE_URL or "").strip()
        if raw.startswith("sqlite:////"):
            return raw.replace("sqlite:////", "/", 1)
        if raw.startswith("sqlite:///"):
            return raw.replace("sqlite:///", "", 1) or "schedule.db"
        return "schedule.db"


# settings 객체를 생성해서 다른 파일들에서 import 해서 사용
settings = Settings()