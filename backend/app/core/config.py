from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    APP_SECRET_KEY: str # For encrypting user API keys

    # Optional: Exchange API keys for direct backend testing/general data
    BYBIT_API_KEY: str | None = None
    BYBIT_API_SECRET: str | None = None
    WOOX_API_KEY: str | None = None
    WOOX_API_SECRET: str | None = None
    HYPERLIQUID_WALLET_ADDRESS: str | None = None # Example, adjust based on actual auth
    HYPERLIQUID_PRIVATE_KEY: str | None = None    # Example, adjust
    PARADEX_JWT: str | None = None                # Example, adjust

    LOG_LEVEL: str = "info"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'ignore' # Ignore extra fields from .env

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
