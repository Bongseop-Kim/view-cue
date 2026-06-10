"""환경 변수 기반 설정 (pydantic-settings)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # 서버
    app_env: str = "local"
    debug: bool = True

    # OpenAI (Whisper STT + GPT 리포트)
    openai_api_key: str = ""
    openai_stt_model: str = "whisper-1"
    openai_llm_model: str = "gpt-4o"

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "interview-videos"

    # 분석 파이프라인
    temp_dir: str = "/tmp/view-cue"
    video_retention_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
