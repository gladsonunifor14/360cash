from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração carregada de variáveis de ambiente (12-factor)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CASH360_", extra="ignore")

    app_name: str = "360cash API"
    environment: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://cash360:cash360@localhost:5432/cash360"

    # JWT
    jwt_secret: str = Field(default="change-me-in-production-min-32-chars!!", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    otp_token_minutes: int = 10  # validade do token intermediário (senha OK, falta OTP)

    # OTP
    otp_length: int = 6
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5

    # Reset de senha
    password_reset_minutes: int = 30
    password_min_length: int = 10

    # E-mail (Resend)
    resend_api_key: str = ""
    email_from: str = "360cash <contato@360cash.tech>"
    frontend_url: str = "https://app.360cash.tech"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "https://app.360cash.tech"]

    # Rate limit (requisições por janela por IP+rota sensível)
    rate_limit_auth_per_minute: int = 10

    # Uploads
    upload_max_bytes: int = 15 * 1024 * 1024
    storage_dir: str = "./storage"

    # CNPJ
    cnpj_providers: list[str] = [
        "https://brasilapi.com.br/api/cnpj/v1/{cnpj}",
        "https://receitaws.com.br/v1/cnpj/{cnpj}",
    ]

    # Open Finance via agregador (Pluggy)
    pluggy_client_id: str = ""
    pluggy_client_secret: str = ""

    # IA de classificação (opcional): se definido, usa Claude como fallback
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
