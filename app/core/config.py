from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "코스톡 API"
    app_env: str = "development"
    database_path: str = "./coursetalk.db"
    frontend_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    auto_import_data: bool = True
    data_zip_path: str = "./data/data.zip"
    import_regions: Annotated[list[str], NoDecode] = ["광주_전라권"]

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("frontend_origins", "import_regions", mode="before")
    @classmethod
    def split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def resolved_database_path(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def resolved_data_zip_path(self) -> Path:
        path = Path(self.data_zip_path)
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
