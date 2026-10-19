from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = "postgresql+psycopg://hiring:hiring_local@localhost:5433/hiring"
    web_origin: str = "http://localhost:3002"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4.1-mini-2025-04-14"
    openai_timeout_seconds: float = Field(default=45, gt=0, le=120)
    openai_max_retries: int = Field(default=1, ge=0, le=3)
    openai_max_output_tokens: int = Field(default=1000, ge=128, le=4000)
    worker_lease_seconds: int = Field(default=300, ge=30, le=3600)
    worker_poll_seconds: float = Field(default=2, gt=0, le=30)
    worker_retry_base_seconds: int = Field(default=10, ge=1, le=300)
    worker_retry_max_seconds: int = Field(default=300, ge=1, le=3600)
    worker_retry_attempts: int = Field(default=3, ge=1, le=10)
    hr_demo_email: str = "hr@example.test"
    hr_demo_name: str = "Demo HR Reviewer"
    hr_demo_password: SecretStr = SecretStr("")
    hr_session_hours: int = Field(default=8, ge=1, le=24)
    hr_audio_root: Path = ROOT / "var/uploads"
    candidate_audio_dir: Path = ROOT / "var/uploads/candidate-audio"
    candidate_max_audio_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)


settings = Settings()
