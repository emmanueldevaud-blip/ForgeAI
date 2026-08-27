from functools import lru_cache
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "ForgeAI Demo"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = Field(..., description="Clé secrète pour JWT (obligatoire)")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = Field(..., description="URL de connexion MySQL (obligatoire)")
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Local Auth
    AUTH_LOCAL_ENABLED: bool = True
    BCRYPT_ROUNDS: int = 12

    # Active Directory / LDAP
    AD_ENABLED: bool = False
    AD_SERVER: str = ""
    AD_PORT: int = 636
    AD_USE_SSL: bool = True
    AD_BASE_DN: str = ""
    AD_USER_DN: str = ""
    AD_USER_SEARCH_FILTER: str = "(sAMAccountName={username})"
    AD_GROUP_SEARCH_BASE: str = ""
    AD_ADMIN_GROUP: str = ""
    AD_BIND_USER: str = ""
    AD_BIND_PASSWORD: str = ""
    AD_CONNECT_TIMEOUT: int = 10
    AD_RECEIVE_TIMEOUT: int = 10
    AD_GROUP_MAPPING: dict = Field(
        default_factory=lambda: {
            "admin": "AD_GROUP_ADMIN",
            "user": "AD_GROUP_USER",
        }
    )

    # Security
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @property
    def ad_url(self) -> str:
        protocol = "ldaps" if self.AD_USE_SSL else "ldap"
        return f"{protocol}://{self.AD_SERVER}:{self.AD_PORT}"


@lru_cache
def get_settings() -> Settings:
    return Settings()