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
    RATE_LIMIT_ENABLED: bool = False
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
    SPORT_EVENING_ANALYSIS_TIME: str = "20:00"
    SPORT_ACTIVITY_ANALYSIS_ENABLED: bool = True
    SPORT_ACTIVITY_ANALYSIS_DELAY_MINUTES: int = 15
    SPORT_ANALYSIS_TIMEZONE: str = "Europe/Paris"

    # Conseils ponctuels du coach (hors analyses) : maximum par jour.
    COACH_TIP_DAILY_LIMIT: int = 2

    # Agent Sport (orchestration autonome au-dessus des analyses existantes).
    # Desactiver pour retomber automatiquement sur les jobs historiques.
    SPORT_AGENT_ENABLED: bool = True
    SPORT_AGENT_MAX_STEPS: int = 5
    SPORT_AGENT_MAX_TOOL_CALLS: int = 16
    SPORT_AGENT_TIMEOUT_SECONDS: int = 60

    # Agent Développement (orchestration OpenCode pour le développement ForgeAI).
    DEVELOPMENT_AGENT_ENABLED: bool = False
    DEVELOPMENT_AGENT_MAX_STEPS: int = 10
    DEVELOPMENT_AGENT_MAX_TOOL_CALLS: int = 20
    DEVELOPMENT_AGENT_TIMEOUT_SECONDS: int = 300
    OPENCODE_BIN: str = ""
    OPENCODE_WORK_DIR: str = "."
    OPENCODE_ENABLED: bool = True

    # AI Model Router (routage intelligent multi-providers)
    AI_ROUTER_ENABLED: bool = True
    AI_ROUTER_PREFER_FREE: bool = True
    AI_ROUTER_COOLDOWN_SECONDS: float = 300.0

    # Web Search (pour l'Agent Sport - recherche autonome d'informations)
    WEB_SEARCH_ENABLED: bool = True
    WEB_SEARCH_PROVIDER: str = "brave"  # brave, duckduckgo, serper
    WEB_SEARCH_API_KEY: str = ""
    WEB_SEARCH_MAX_RESULTS: int = 8
    WEB_SEARCH_TIMEOUT_SECONDS: float = 15.0
    WEB_SEARCH_FALLBACK_ENABLED: bool = True

    # Web Search Cache
    WEB_SEARCH_CACHE_ENABLED: bool = True
    WEB_SEARCH_CACHE_TTL_SECONDS: int = 3600

    # Notifications (Web Push vers le telephone -> repliquee sur la montre Garmin)
    NOTIFICATION_VAPID_PUBLIC_KEY: str = ""
    NOTIFICATION_VAPID_PRIVATE_KEY: str = ""
    NOTIFICATION_VAPID_SUBJECT: str = ""

    # Photos (gestionnaire de photos personuelles auto-heberge)
    PHOTO_ENABLED: bool = True
    PHOTO_STORAGE_PATH: str = "data/photos"
    # Vide = sous-dossier "thumbs" dans PHOTO_STORAGE_PATH.
    PHOTO_THUMBNAIL_PATH: str = ""
    PHOTO_MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # octets
    # Largeurs des miniatures (px), de la plus petite a la plus grande.
    PHOTO_THUMBNAIL_SIZES: str = "tiny:96,small:256,medium:640,large:1280,preview:2048"
    # File de taches d'arriere-plan (ingest, analyse IA, ...).
    PHOTO_BACKGROUND_JOBS: bool = True
    PHOTO_JOB_POLL_SECONDS: float = 2.0
    PHOTO_JOB_BATCH: int = 8
    PHOTO_JOB_MAX_ATTEMPTS: int = 3
    # Analyse IA (classification / tags). "metadata" = analyseur local,
    # les analyseurs visuels (local/LLM) sont ajoutables sans changer le pipeline.
    PHOTO_ANALYSIS_ENABLED: bool = True
    PHOTO_ANALYZER: str = "metadata"
    # Score de qualite (nettetee / exposition / cadrage) ajoute au resultat
    # de l'analyse, calcule sur une miniature (jamais sur l'original).
    PHOTO_QUALITY_ENABLED: bool = True
    # Embedding image pour « photos similaires » : provider local par defaut,
    # aucun appel réseau. Le vecteur est stocké en JSON dans la base.
    PHOTO_EMBEDDING_ENABLED: bool = True
    PHOTO_EMBEDDING_PROVIDER: str = "local_grid"
    # Miniature utilisée pour l'analyse et l'embedding (performance).
    PHOTO_ANALYSIS_THUMB_SIZE: str = "medium"
    # Detection de visages (local-first : heuristique locale sans modele).
    # Desactive, la detection et le regroupement ne s'executent pas.
    PHOTO_FACE_ENABLED: bool = True
    # Détecteur de visages : "local_heuristic" (Pillow, aucun réseau) —
    # un moteur réel pourra être ajouté au registre sans toucher au pipeline.
    PHOTO_FACE_DETECTOR: str = "local_heuristic"
    # Regroupement automatique des visages en groupes anonymes (« Personne N »).
    PHOTO_FACE_GROUPING_ENABLED: bool = True
    # Similarité cosinus minimale pour rejoindre un groupe anonyme existant
    # / pour fusionner deux groupes anonymes (seuil plus exigeant).
    PHOTO_FACE_GROUP_THRESHOLD: float = 0.90
    PHOTO_FACE_GROUP_MERGE_THRESHOLD: float = 0.97
    # Recherche naturelle assistee par l'AI Gateway (retombe sur l'heuristique).
    PHOTO_AI_SEARCH_ENABLED: bool = True
    # Resolution des lieux via une API externe (opt-in, resultats caches en base).
    PHOTO_GEOCODING_ENABLED: bool = False
    # V3 — Stockage des originaux : "local" (volume applicatif) ou "nas"
    # (repertoire monte, ex. /mnt/synology/photos). Les miniatures et les
    # versions retouchees restent toujours locales.
    PHOTO_STORAGE_BACKEND: str = "local"
    # Racine des originaux NAS (chemin deja monte par le systeme — ForgeAI
    # n'ouvre aucune connexion SMB/NFS). Ignore si PHOTO_STORAGE_BACKEND=local.
    PHOTO_NAS_PATH: str = ""
    # Scan automatique (en arriere-plan) du repertoire NAS.
    PHOTO_NAS_SCAN_ENABLED: bool = False
    # Intervalle minimal entre deux scans automatiques.
    PHOTO_NAS_SCAN_INTERVAL_SECONDS: int = 300

    @property
    def ad_url(self) -> str:
        protocol = "ldaps" if self.AD_USE_SSL else "ldap"
        return f"{protocol}://{self.AD_SERVER}:{self.AD_PORT}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
