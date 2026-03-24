# app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Schedule API"
    GEMINI_API_KEY: str
    DATABASE_URL: str

    class Config:
        env_file = ".env"  # .env 파일을 읽어오도록 설정


# settings 객체를 생성해서 다른 파일들에서 import 해서 사용
settings = Settings()