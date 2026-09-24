"""AI Gateway centralisée de ForgeAI.

Interface stable pour les modules applicatifs :

    from app.services.ai_gateway import ai_gateway

    response = await ai_gateway.generate(
        prompt="Analyse cette demande",
        task_type="general",
    )

La passerelle gère seule le choix du fournisseur, du modèle, les retries,
les quotas, le fallback et la journalisation. Les modules ne manipulent
jamais de clés API ni de spécificités de fournisseurs.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from functools import lru_cache

import httpx

from app.core.config import Settings, get_settings
from app.services.ai_gateway.errors import (
    AIAuthenticationError,
    AIGatewayError,
    AINoProviderAvailable,
    AIProviderUnavailable,
    AIQuotaExceeded,
    AIRequestTimeout,
)
from app.services.ai_gateway.models import resolve_model
from app.services.ai_gateway.providers import BaseAIProvider, build_providers
from app.services.ai_gateway.stats import StatsStore

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_ORDER = ["groq", "gemini", "openrouter"]
TEMPORARY_ERROR_COOLDOWN_SECONDS = 60.0
QUOTA_ERROR_COOLDOWN_SECONDS = 300.0


@dataclass
class AIResponse:
    """Réponse de la passerelle + métadonnées d'exécution."""

    text: str
    provider_used: str
    model_used: str
    tokens_input: int | None = None
    tokens_output: int | None = None
    latency: float = 0.0
    fallback_used: bool = False
    quota_status: dict[str, str] = field(default_factory=dict)


class AIGateway:
    """Orchestrateur : sélection, retries, fallback, quotas, logs."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        stats: StatsStore | None = None,
        providers: dict[str, BaseAIProvider] | None = None,
    ):
        self.settings = settings or get_settings()
        self._client = client
        self.stats = stats or StatsStore()
        self._providers = providers or build_providers(self.settings, client)

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        prompt: str = "",
        system_prompt: str | None = None,
        model: str = "auto",
        task_type: str = "general",
        temperature: float | None = None,
        max_tokens: int | None = None,
        preferred_provider: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AIResponse:
        if not self.settings.AI_GATEWAY_ENABLED:
            raise AINoProviderAvailable("AI Gateway désactivée (AI_GATEWAY_ENABLED=false)")

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        elif prompt and prompt.strip():
            messages.append({"role": "user", "content": prompt})
        else:
            raise ValueError("prompt vide")

        if not model or model.lower() == "auto":
            model = self.settings.AI_DEFAULT_MODEL or "auto"

        order = self._resolve_order(preferred_provider)
        candidates = [name for name in order if self._is_candidate(name)]
        if not candidates:
            logger.warning("[AI-GATEWAY] status=no_provider_available order=%s", ",".join(order))
            raise AINoProviderAvailable(
                "Aucun fournisseur IA configuré et disponible", errors=[]
            )

        errors: list[Exception] = []
        started = asyncio.get_event_loop().time()
        fallback_used = False

        for index, provider_name in enumerate(candidates):
            provider = self._providers[provider_name]
            resolved_model = resolve_model(self.settings, provider_name, task_type, model)

            try:
                text, tokens_in, tokens_out = await self._call_with_retries(
                    provider, resolved_model, messages, temperature, max_tokens
                )
            except AIGatewayError as exc:
                errors.append(exc)
                cooldown = self._cooldown_for(exc)
                status = self._status_for(exc)
                self.stats.record_error(provider_name, resolved_model, status, cooldown)
                fallback_used = True
                next_name = candidates[index + 1] if index + 1 < len(candidates) else None
                logger.warning(
                    "[AI-GATEWAY] provider=%s model=%s status=%s fallback=%s",
                    provider_name,
                    resolved_model,
                    status,
                    next_name or "none",
                )
                continue

            latency = asyncio.get_event_loop().time() - started
            self.stats.record_request(provider_name, resolved_model)
            self.stats.record_success(provider_name, resolved_model, tokens_in, tokens_out)
            if fallback_used:
                self.stats.record_fallback(provider_name)
            logger.info(
                "[AI-GATEWAY] provider=%s model=%s status=success latency=%.3fs fallback=%s",
                provider_name,
                resolved_model,
                latency,
                fallback_used,
            )
            return AIResponse(
                text=text,
                provider_used=provider_name,
                model_used=resolved_model,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                latency=round(latency, 3),
                fallback_used=fallback_used,
                quota_status=self.stats.quota_status(),
            )

        logger.error(
            "[AI-GATEWAY] status=all_providers_failed errors=%s",
            [type(e).__name__ for e in errors],
        )
        raise AINoProviderAvailable(
            "Tous les fournisseurs IA configurés ont échoué", errors=errors
        )

    def get_stats(self) -> dict:
        """Statistiques d'utilisation (aucun secret, aucun prompt)."""
        return self.stats.snapshot()

    # ------------------------------------------------------------------ #
    # Internes
    # ------------------------------------------------------------------ #

    def _resolve_order(self, preferred_provider: str | None) -> list[str]:
        order = [p.strip().lower() for p in self.settings.AI_PROVIDER_ORDER.split(",") if p.strip()]
        order = order or list(DEFAULT_PROVIDER_ORDER)
        preferred = (preferred_provider or "").strip().lower()
        if not preferred or preferred == "auto":
            default = (self.settings.AI_DEFAULT_PROVIDER or "").strip().lower()
            if default and default != "auto":
                preferred = default
        if preferred and preferred in PROVIDER_NAMES:
            order = [preferred] + [p for p in order if p != preferred]
        return order

    def _is_candidate(self, name: str) -> bool:
        provider = self._providers.get(name)
        if provider is None or not provider.is_available:
            return False
        return self.stats.is_available(name)

    async def _call_with_retries(
        self,
        provider: BaseAIProvider,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, int | None, int | None]:
        attempts = max(1, self.settings.AI_MAX_RETRIES + 1)
        last_error: AIGatewayError | None = None
        for attempt in range(attempts):
            try:
                return await provider.chat(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except (AIRequestTimeout, AIQuotaExceeded) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    delay = self.settings.AI_RETRY_BACKOFF_SECONDS * (2**attempt)
                    logger.info(
                        "[AI-GATEWAY] provider=%s status=retry attempt=%d/%d delay=%.1fs",
                        provider.name,
                        attempt + 1,
                        attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise last_error from exc
            except AIProviderUnavailable as exc:
                if exc.retryable and attempt < attempts - 1:
                    delay = self.settings.AI_RETRY_BACKOFF_SECONDS * (2**attempt)
                    logger.info(
                        "[AI-GATEWAY] provider=%s status=retry attempt=%d/%d delay=%.1fs",
                        provider.name,
                        attempt + 1,
                        attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    last_error = exc
                    continue
                raise
        raise last_error if last_error else AINoProviderAvailable()

    @staticmethod
    def _cooldown_for(exc: AIGatewayError) -> float:
        if isinstance(exc, AIQuotaExceeded):
            return QUOTA_ERROR_COOLDOWN_SECONDS
        if isinstance(exc, AIAuthenticationError):
            return QUOTA_ERROR_COOLDOWN_SECONDS
        if isinstance(exc, (AIRequestTimeout, AIProviderUnavailable)):
            return TEMPORARY_ERROR_COOLDOWN_SECONDS
        return 0.0

    @staticmethod
    def _status_for(exc: AIGatewayError) -> str:
        if isinstance(exc, AIQuotaExceeded):
            return "quota_exceeded"
        if isinstance(exc, AIAuthenticationError):
            return "auth_error"
        if isinstance(exc, AIRequestTimeout):
            return "timeout"
        if isinstance(exc, AIProviderUnavailable):
            return "unavailable"
        return type(exc).__name__.lower()


PROVIDER_NAMES = ("groq", "gemini", "openrouter")


class AIGatewayReference:
    """Référence paresseuse : délègue à l'instance singleton à chaque appel."""

    def __getattr__(self, item):
        return getattr(get_ai_gateway(), item)

    async def generate(self, *args, **kwargs) -> AIResponse:
        return await get_ai_gateway().generate(*args, **kwargs)


@lru_cache
def get_ai_gateway() -> AIGateway:
    """Instance singleton de la passerelle (configuration chargée une fois)."""
    return AIGateway()


ai_gateway = AIGatewayReference()
