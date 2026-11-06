"""集中配置：全部来自环境变量（.env），代码里不出现任何密钥。"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    demo_mode: bool = False

    database_url: str = "postgresql+asyncpg://silkroad@postgres:5432/silkroad"  # 密码只经 .env 注入
    redis_url: str = "redis://redis:6379/0"
    task_mode: Literal["arq", "inline"] = "arq"

    # 鉴权
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: str = "silkroad-audit"
    access_token_ttl_s: int = 900
    refresh_token_ttl_s: int = 7 * 24 * 3600
    cookie_secure: bool = True
    login_max_failures: int = 5
    login_lock_s: int = 900

    # 限流（每分钟）
    rl_login_per_min: int = 10
    rl_upload_per_min: int = 20
    rl_default_per_min: int = 300

    # 数据加密：主密钥（KEK）32 字节 base64，key id 便于轮换
    data_kek: str
    data_kek_id: str = "k1"
    storage_dir: Path = Path("/data/storage")
    retention_days: int = 30

    # 文件约束
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pages: int = 10

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # 模型链路（M1 接入，M0 只展示配置）
    llm_provider_chain: list[str] = ["deepseek", "qwen", "ollama"]
    ocr_engine: str = "rapidocr-ppocrv4"

    # 首次启动引导管理员（仅在用户表为空时生效）
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None

    @field_validator("data_kek")
    @classmethod
    def _kek_len(cls, v: str) -> str:
        if len(base64.b64decode(v)) != 32:
            raise ValueError("DATA_KEK 必须是 32 字节的 base64")
        return v

    @property
    def kek_bytes(self) -> bytes:
        return base64.b64decode(self.data_kek)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
