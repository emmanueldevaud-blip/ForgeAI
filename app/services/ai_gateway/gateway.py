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
import json
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Awaitable, Callable

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
from app.services.ai_gateway.tool_protocol import build_tool_instructions, parse_tool_calls

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_ORDER = ["groq", "gemini", "openrouter"]
TEMPORARY_ERROR_COOLDOWN_SECONDS = 60.0
QUOTA_ERROR_COOLDOWN_SECONDS = 300.0
DEFAULT_MAX_TOOL_ROUNDS = 4
DEFAULT_MAX_TOOL_CALLS = 16


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
    # Traçabilité des appels d'outils exécutés pendant la requête (noms + issue).
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


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
        tools: list[dict] | None = None,
        tool_executor: Callable[[str, dict], Awaitable[Any]] | None = None,
        max_tool_rounds: int | None = None,
        max_tool_calls: int | None = None,
    ) -> AIResponse:
        """Appel IA. Les paramètres d'outils sont optionnels : sans ``tools``,
        le comportement est strictement identique aux versions précédentes."""
        if not self.settings.AI_GATEWAY_ENABLED:
            raise AINoProviderAvailable("AI Gateway désactivée (AI_GATEWAY_ENABLED=false)")

        if tools and tool_executor is None:
            raise ValueError("tool_executor est requis lorsque tools est fourni")

        system = system_prompt
        if tools:
            system = f"{system or ''}{build_tool_instructions(tools)}"

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            messages.extend(history)
        elif prompt and prompt.strip():
            messages.append({"role": "user", "content": prompt})
        else:
            raise ValueError("prompt vide")

        if not model or model.lower() == "auto":
            model = self.settings.AI_DEFAULT_MODEL or "auto"

        response = await self._dispatch(messages, model, task_type, temperature, max_tokens, preferred_provider)
        if not tools:
            return response
        return await self._run_tool_loop(
            response,
            messages,
            model,
            task_type,
            temperature,
            max_tokens,
            preferred_provider,
            tool_executor,
            max_tool_rounds,
            max_tool_calls,
        )

    async def _run_tool_loop(
        self,
        response: AIResponse,
        messages: list[dict[str, str]],
        model: str,
        task_type: str,
        temperature: float | None,
        max_tokens: int | None,
        preferred_provider: str | None,
        tool_executor: Callable[[str, dict], Awaitable[Any]] | None,
        max_tool_rounds: int | None,
        max_tool_calls: int | None,
    ) -> AIResponse:
        """Boucle modèle -> outils -> modèle jusqu'à la décision finale."""
        budget_rounds = max_tool_rounds if max_tool_rounds is not None else DEFAULT_MAX_TOOL_ROUNDS
        budget_calls = max_tool_calls if max_tool_calls is not None else DEFAULT_MAX_TOOL_CALLS
        tokens_input = response.tokens_input or 0
        tokens_output = response.tokens_output or 0
        executed: list[dict[str, Any]] = []
        rounds = 0
        exhausted = False

        while True:
            pending = parse_tool_calls(response.text)
            if not pending:
                break
            if rounds >= budget_rounds or len(executed) >= budget_calls:
                exhausted = True
                break
            rounds += 1
            results = [await self._execute_tool_call(tool_executor, call, executed, budget_calls) for call in pending]
            messages.append({"role": "assistant", "content": response.text})
            messages.append({
                "role": "user",
                "content": "Résultats des outils (JSON) :\n" + json.dumps(results, ensure_ascii=False, default=str),
            })
            response = await self._dispatch(messages, model, task_type, temperature, max_tokens, preferred_provider)
            tokens_input += response.tokens_input or 0
            tokens_output += response.tokens_output or 0

        if exhausted:
            # Dernier tour : les appels restants sont exécutés, puis le modèle
            # est invité à conclure sans nouvel outil.
            results = [await self._execute_tool_call(tool_executor, call, executed, budget_calls) for call in pending]
            messages.append({"role": "assistant", "content": response.text})
            messages.append({
                "role": "user",
                "content": (
                    "Résultats des outils (JSON) :\n" + json.dumps(results, ensure_ascii=False, default=str)
                    + "\n\nBudget d'outils épuisé : conclus MAINTENANT avec {\"final\": ...} "
                    "sans demander d'autre outil."
                ),
            })
            response = await self._dispatch(messages, model, task_type, temperature, max_tokens, preferred_provider)
            tokens_input += response.tokens_input or 0
            tokens_output += response.tokens_output or 0

        response.tokens_input = tokens_input
        response.tokens_output = tokens_output
        response.tool_calls = executed
        return response

    async def _execute_tool_call(
        self,
        tool_executor: Callable[[str, dict], Awaitable[Any]] | None,
        call: dict[str, Any],
        executed: list[dict[str, Any]],
        budget_calls: int,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {"name": call.get("name"), "arguments": call.get("arguments") or {}}
        if tool_executor is None:
            entry.update({"ok": False, "error": "aucun_executant"})
        elif len(executed) >= budget_calls:
            entry.update({"ok": False, "error": "budget_outil_atteint"})
        else:
            started = time.monotonic()
            try:
                result = await tool_executor(entry["name"], entry["arguments"])
            except Exception as exc:  # un outil en échec n'interrompt pas la boucle
                entry.update({"ok": False, "error": str(exc) or type(exc).__name__})
            else:
                entry.update({"ok": True, "result": result})
            entry["duration_ms"] = int((time.monotonic() - started) * 1000)
        if entry.get("ok"):
            executed.append(entry)
        return entry

    async def _dispatch(
        self,
        messages: list[dict[str, str]],
        model: str,
        task_type: str,
        temperature: float | None,
        max_tokens: int | None,
        preferred_provider: str | None,
    ) -> AIResponse:
        """Sélection du fournisseur, retries, fallback, quotas et journalisation."""
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
