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

    model_config = SettingsConfigDict(env_file=".env")  # .env 파일을 읽어오도록 설정

    @property
    def cors_origin_list(self) -> list[str]:
        values = [v.strip() for v in self.ALLOWED_ORIGINS.split(",") if v.strip()]
        return values or ["*"]

    @property
    def trusted_host_list(self) -> list[str]:
        values = [v.strip() for v in self.ALLOWED_HOSTS.split(",") if v.strip()]
        return values or ["*"]


# settings 객체를 생성해서 다른 파일들에서 import 해서 사용
settings = Settings()