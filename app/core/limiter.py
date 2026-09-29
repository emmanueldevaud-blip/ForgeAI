"""Limiteur de requêtes partagé (slowapi).

Déplacé depuis app/main.py pour être importable par les routers (ex. auth)
sans importer app.main (import circulaire).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.RATE_LIMIT_ENABLED,
    default_limits=[
        f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW_SECONDS}seconds"
    ],
)
