"""Catalogue centralisé des modèles IA par type de tâche.

Point unique de configuration des modèles : pour ajouter ou changer un
modèle, modifier ce catalogue ou passer par les variables d'environnement
GROQ_MODEL / GEMINI_MODEL / OPENROUTER_MODEL (qui priment sur le catalogue).
"""

from app.core.config import Settings

DEFAULT_TASK_TYPE = "general"

# task_type -> provider -> modèle
MODEL_CATALOG: dict[str, dict[str, str]] = {
    "general": {
        "groq": "openai/gpt-oss-120b",
        "gemini": "gemini-2.0-flash",
        "openrouter": "openai/gpt-4o-mini",
    },
    "fast": {
        "groq": "openai/gpt-oss-20b",
        "gemini": "gemini-2.0-flash",
        "openrouter": "openai/gpt-4o-mini",
    },
    "reasoning": {
        "groq": "openai/gpt-oss-120b",
        "gemini": "gemini-2.5-flash",
        "openrouter": "anthropic/claude-3.5-sonnet",
    },
    "coding": {
        "groq": "qwen/qwen3.8-27b",
        "gemini": "gemini-2.0-flash",
        "openrouter": "qwen/qwen-2.5-coder-32b-instruct",
    },
}

# Override fournisseur défini par variable d'environnement
_ENV_MODEL_FIELDS = {
    "groq": "GROQ_MODEL",
    "gemini": "GEMINI_MODEL",
    "openrouter": "OPENROUTER_MODEL",
}


def resolve_model(settings: Settings, provider: str, task_type: str, model: str | None) -> str:
    """Résout le modèle effectif pour un fournisseur.

    Priorité :
    1. modèle explicite passé par l'appelant (hors "auto") ;
    2. variable d'environnement du fournisseur (GROQ_MODEL, ...) ;
    3. catalogue du type de tâche ;
    4. catalogue "general".
    """
    if model and model.lower() != "auto":
        return model

    env_value = getattr(settings, _ENV_MODEL_FIELDS.get(provider, ""), "")
    if env_value:
        return env_value

    task_models = MODEL_CATALOG.get(task_type) or MODEL_CATALOG[DEFAULT_TASK_TYPE]
    return task_models.get(provider) or MODEL_CATALOG[DEFAULT_TASK_TYPE][provider]
