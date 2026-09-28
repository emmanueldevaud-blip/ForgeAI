from functools import lru_cache

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
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

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

    # AI Gateway (passerelle IA centralisée)
    AI_GATEWAY_ENABLED: bool = True
    AI_DEFAULT_PROVIDER: str = "auto"
    AI_DEFAULT_MODEL: str = "auto"
    AI_PROVIDER_ORDER: str = "groq,gemini,openrouter"
    AI_TIMEOUT_SECONDS: float = 30.0
    AI_MAX_RETRIES: int = 2
    AI_RETRY_BACKOFF_SECONDS: float = 1.0

    # Provider Groq
    GROQ_ENABLED: bool = True
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = ""

    # Provider Google Gemini
    GEMINI_ENABLED: bool = True
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_MODEL: str = ""

    # Provider OpenRouter
    OPENROUTER_ENABLED: bool = True
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = ""

    # Security
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Sport - analyses automatiques (matin / soir / apres activite)
    SPORT_ANALYSIS_ENABLED: bool = True
    SPORT_MORNING_ANALYSIS_ENABLED: bool = True
    SPORT_MORNING_ANALYSIS_TIME: str = "07:00"
    # L'analyse du matin attend la nuit synchronisee jusqu'a cette heure
    # (au plus tard) ; au dela elle est produite avec les donnees disponibles.
    SPORT_MORNING_ANALYSIS_DEADLINE: str = "10:00"
    SPORT_EVENING_ANALYSIS_ENABLED: bool = True
    SPORT_EVENING_ANALYSIS_TIME: str = "20:30"
    SPORT_ACTIVITY_ANALYSIS_ENABLED: bool = True
    SPORT_ACTIVITY_ANALYSIS_DELAY_MINUTES: int = 15
    SPORT_ANALYSIS_TIMEZONE: str = "Europe/Paris"

    # Notifications (Web Push vers le telephone -> repliquee sur la montre Garmin)
    NOTIFICATION_VAPID_PUBLIC_KEY: str = ""
    NOTIFICATION_VAPID_PRIVATE_KEY: str = ""
    NOTIFICATION_VAPID_SUBJECT: str = ""

    @property
    def ad_url(self) -> str:
        protocol = "ldaps" if self.AD_USE_SSL else "ldap"
        return f"{protocol}://{self.AD_SERVER}:{self.AD_PORT}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
