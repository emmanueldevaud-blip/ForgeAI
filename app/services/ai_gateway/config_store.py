"""Persistance des paramètres de l'AI Gateway (table ``module_configs``).

Les paramètres LLM (activateurs, clés API, modèles, retries) sont stockés
côté serveur dans ``module_configs`` (module « administration »), sur la
même couche que la configuration SMTP. Les valeurs DB font foi sur les
variables d'environnement ; l'overlay est appliqué sur l'instance
``Settings`` partagée afin que l'AI Gateway (singleton) les voie à chaud.

Les clés API ne sont jamais renvoyées au frontend : seuls des booléens
``*_configured`` sortent via l'API.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.module import Module, ModuleConfig

# Champs Settings exposés dans la page « Assistant IA ».
AI_SETTINGS_FIELDS: tuple[str, ...] = (
    "AI_GATEWAY_ENABLED",
    "AI_DEFAULT_PROVIDER",
    "AI_DEFAULT_MODEL",
    "AI_PROVIDER_ORDER",
    "AI_TIMEOUT_SECONDS",
    "AI_MAX_RETRIES",
    "AI_RETRY_BACKOFF_SECONDS",
    "GROQ_ENABLED",
    "GROQ_API_KEY",
    "GROQ_BASE_URL",
    "GROQ_MODEL",
    "GEMINI_ENABLED",
    "GEMINI_API_KEY",
    "GEMINI_BASE_URL",
    "GEMINI_MODEL",
    "OPENROUTER_ENABLED",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODEL",
)

SECRET_FIELDS = frozenset({"GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"})


def db_key(field: str) -> str:
    """Clé module_configs d'un champ Settings (ex. GROQ_API_KEY -> groq_api_key)."""
    return field.lower()


def convert_value(field: str, raw: str):
    """Convertit une valeur stockée (chaîne) vers le type du champ Settings."""
    annotation = Settings.model_fields[field].annotation
    if annotation is bool:
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if annotation is int:
        return int(float(raw))
    if annotation is float:
        return float(raw)
    return str(raw)


async def load_overrides(db: AsyncSession) -> dict[str, str]:
    """Valeurs IA stockées en DB (clé = db_key, valeur brute chaîne)."""
    keys = [db_key(field) for field in AI_SETTINGS_FIELDS]
    result = await db.execute(
        select(ModuleConfig)
        .join(Module)
        .where(Module.code == "administration", ModuleConfig.key.in_(keys))
    )
    return {config.key: config.value for config in result.scalars().all() if config.value is not None}


def apply_overrides(settings: Settings, overrides: dict[str, str]) -> None:
    """Applique les valeurs DB sur l'instance Settings (overlay à chaud)."""
    by_key = {db_key(field): field for field in AI_SETTINGS_FIELDS}
    for key, raw in overrides.items():
        field = by_key.get(key)
        if field is None or raw is None:
            continue
        try:
            setattr(settings, field, convert_value(field, raw))
        except (ValueError, TypeError):
            continue


async def apply_from_db(db: AsyncSession) -> None:
    """Recharge l'overlay DB sur l'instance Settings partagée (runtime)."""
    overrides = await load_overrides(db)
    apply_overrides(get_settings(), overrides)
