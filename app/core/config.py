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
    # 사진/문서 업로드 저장 루트
    UPLOADS_DIR: str = "uploads"
    # 세션 만료 기간(일)
    SESSION_TTL_DAYS: int = 30
    # 외출 복귀 시각(until_time) 비교에 사용. 브라우저는 로컬 날짜+시각으로 저장하므로 서버가 UTC여도 맞춤.
    APP_TIMEZONE: str = "Asia/Seoul"

    # 예전 .env 값이 남아 있어도 기동되게 무시
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
