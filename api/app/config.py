from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "local"
    app_base_url: str = "http://localhost:5173"
    secret_key: str = "dev-only-change-me"

    # Local default points at the pgserver unix socket created by scripts/dev_db.py.
    database_url: str = "postgresql+psycopg://postgres@/postgres?host=/tmp/opencode/pgdata"

    storage_backend: str = "local"
    local_storage_dir: str = "/tmp/opencode/storage"

    s3_endpoint: str = ""
    s3_region: str = "ap-south-1"
    s3_bucket: str = "customs-ai-local"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    google_cloud_project: str = ""
    vertex_location: str = "asia-south1"
    vertex_model: str = ""
    ai_monthly_cap_paise: int = 500_000

    max_upload_mb: int = 25
    max_pages: int = 40
    session_ttl_hours: int = 8
    retention_days: int = 180

    demo_exec_password: str = "demo-exec-2026"
    demo_manager_password: str = "demo-manager-2026"

    @property
    def is_local(self) -> bool:
        return self.app_env in {"local", "test"}

    @property
    def static_dir(self) -> Path:
        return Path(__file__).resolve().parent / "static"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
