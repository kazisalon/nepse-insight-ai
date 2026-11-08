from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NEPSE Insight AI"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://nepse:nepse_dev_password@localhost:5432/nepse_insight"
    cors_origins: list[str] = ["http://localhost:5173"]
    model_dir: str = "artifacts"

    default_horizon_days: int = 10
    default_return_threshold: float = 0.03
    min_history_days: int = 60
    min_avg_turnover: float = 500_000.0
    max_data_staleness_days: int = 10
    buy_probability: float = 0.45
    sell_probability: float = 0.45
    min_confidence: float = 0.40
    min_edge: float = 0.10

    @property
    def model_path(self) -> Path:
        path = Path(self.model_dir)
        return path if path.is_absolute() else BASE_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
