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
    cors_origins: list[str] = ["https://localhost:3000"]

    # 模型链路：密钥无默认，测试不访问外网
    llm_provider_chain: list[str] = ["deepseek", "qwen", "ollama"]
    ocr_engine: str = "rapidocr-ppocrv4"
    deepseek_api_key: str | None = Field(default=None, repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    qwen_api_key: str | None = Field(default=None, repr=False)
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_timeout_s: float = Field(default=25, gt=0, le=120)
    llm_max_retries: int = Field(default=1, ge=0, le=2)
    llm_max_input_chars: int = Field(default=60_000, ge=1000, le=200_000)
    llm_max_tokens: int = Field(default=2048, ge=128, le=8192)
    llm_circuit_failures: int = Field(default=3, ge=1)
    llm_circuit_reset_s: int = Field(default=60, ge=1)
    model_probe_timeout_s: float = Field(default=1, gt=0, le=5)
    heavy_models_enabled: bool = False
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rules_dir: Path = Path(__file__).resolve().parents[2] / "data" / "rules"
    rl_review_per_min: int = 10

    @field_validator("llm_provider_chain")
    @classmethod
    def _chain(cls, value: list[str]) -> list[str]:
        if not value or len(set(value)) != len(value) or set(value) - {"deepseek", "qwen", "ollama"}:
            raise ValueError("LLM_PROVIDER_CHAIN 必须是非空且不重复的提供方白名单")
        return value

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
