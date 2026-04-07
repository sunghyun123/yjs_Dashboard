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
    # 카카오 로그인 (REST API 키·리다이렉트 URI는 카카오 개발자 콘솔과 동일해야 함)
    KAKAO_REST_API_KEY: str = ""
    KAKAO_CLIENT_SECRET: str = ""
    KAKAO_REDIRECT_URI: str = ""
    # 허용 카카오 사용자 목록 JSON 경로 (프로젝트 루트 기준 기본값)
    KAKAO_WHITELIST_PATH: str = "kakao_whitelist.json"
    # HTTPS 리버스 프록시 뒤에서 true (쿠키 Secure)
    COOKIE_SECURE: bool = False
    # 운영 배포 시 true 권장. true면 http 요청을 https로 리다이렉트한다.
    FORCE_HTTPS_REDIRECT: bool = False
    # 문서 생성/추출 템플릿 루트 (templates.json + 파일)
    DOCUMENT_TEMPLATES_DIR: str = "document_templates"
    # 로컬 exe 실행: FastAPI가 돌아가는 PC에서만 동작. 비우면 API 비활성(503).
    LOCAL_APPS_ROOT: str = ""
    LOCAL_APP_HANGUL: str = "HangulGenerator.exe"
    LOCAL_APP_ERP: str = "ERP.exe"

    # 예전 .env(SIGNUP_ENABLED, INITIAL_ADMIN_PASSWORD 등)가 남아 있어도 기동되게 무시
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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