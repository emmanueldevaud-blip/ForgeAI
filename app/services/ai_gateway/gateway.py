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

Le routage intelligent des modèles (cascade OpenCode → Groq → Gemini → OpenRouter)
est intégré via le ModelCascade, configuré via les paramètres IA en base de données.
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
        self._cascade: Any | None = None

    def _get_cascade(self):
        """Instance de ModelCascade partagée par toutes les requêtes de la gateway.

        L'instance est conservée afin que l'état par modèle (cooldown) persiste
        d'une requête à l'autre. L'horloge reste celle de ``time.time`` sauf
        injection explicite en test.
        """
        if self._cascade is None:
            from app.services.ai.model_router import ModelCascade

            self._cascade = ModelCascade(self.settings)
        return self._cascade

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
        """Sélection du fournisseur, retries, fallback, quotas et journalisation.

        D'abord, on essaie le ModelCascade (OpenCode Free → Groq → Gemini → OpenRouter)
        si le routage intelligent est activé. Sinon, on utilise le routage classique.
        """
        # Essayer le ModelCascade de routage intelligent si activé
        if self.settings.AI_ROUTER_ENABLED and (not model or model.lower() == "auto"):
            cascade = None
            candidates: list[dict[str, str]] = []
            try:
                cascade = self._get_cascade()
                cascade._refresh_opencode_models()
                candidates = cascade.build_candidates(
                    task_type=task_type,
                    preferred_provider=self._preferred_name(preferred_provider),
                )
            except Exception as exc:
                # Erreur dans le ModelCascade, on continue avec le routage classique
                logger.warning(
                    "[AI-GATEWAY] model_router_error=%s, fallback classique",
                    exc,
                )
                cascade = None

            if cascade is not None:
                if candidates:
                    logger.info(
                        "[AI-GATEWAY] model_router_selected provider=%s model=%s",
                        candidates[0]["provider"],
                        candidates[0]["model"],
                    )
                    response = await self._dispatch_cascade(
                        cascade, candidates, messages, temperature, max_tokens
                    )
                    if response is not None:
                        return response
                    # Erreur non récupérable pour la cascade : le routage
                    # classique ci-dessous reprend la main.
                else:
                    logger.warning(
                        "[AI-GATEWAY] model_router_no_candidate, fallback classique"
                    )

        # --- Routage classique ---
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

    async def _dispatch_cascade(
        self,
        cascade: Any,
        candidates: list[dict[str, str]],
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int | None,
    ) -> AIResponse | None:
        """Exécute les candidats de la cascade dans l'ordre, appel par appel.

        Retourne la réponse du premier candidat réussi, lève
        ``AINoProviderAvailable`` si la cascade est épuisée, ou retourne
        ``None`` lorsqu'une erreur classée non récupérable impose de reprendre
        le routage classique.

        Chaque tentative est tracée : provider, modèle, attempt, résultat,
        raison de l'échec et candidat suivant (aucune clé API dans les logs).
        """
        from app.services.ai.model_router import should_fallback

        started = asyncio.get_event_loop().time()
        errors: list[Exception] = []
        failed_providers: set[str] = set()
        fallback_used = False
        attempt = 0

        for index, candidate in enumerate(candidates):
            provider_name = candidate["provider"]
            resolved_model = candidate["model"]
            next_candidate = candidates[index + 1] if index + 1 < len(candidates) else None
            next_label = (
                f"{next_candidate['provider']}/{next_candidate['model']}"
                if next_candidate
                else "classic"
            )

            state = cascade._get_model_state(provider_name, resolved_model)
            if not state.can_attempt():
                logger.debug(
                    "[AI-GATEWAY] cascade attempt=0 provider=%s model=%s "
                    "result=skipped failure_reason=model_cooldown fallback=%s",
                    provider_name,
                    resolved_model,
                    next_label,
                )
                continue

            provider = self._providers.get(provider_name)
            if provider is None:
                logger.debug(
                    "[AI-GATEWAY] cascade attempt=0 provider=%s model=%s "
                    "result=skipped failure_reason=provider_not_configured fallback=%s",
                    provider_name,
                    resolved_model,
                    next_label,
                )
                continue
            if not provider.is_available:
                logger.debug(
                    "[AI-GATEWAY] cascade attempt=0 provider=%s model=%s "
                    "result=skipped failure_reason=provider_unavailable fallback=%s",
                    provider_name,
                    resolved_model,
                    next_label,
                )
                continue

            attempt += 1
            try:
                text, tokens_in, tokens_out = await self._call_with_retries(
                    provider, resolved_model, messages, temperature, max_tokens
                )
            except AIGatewayError as exc:
                status = self._status_for(exc)
                recoverable = should_fallback(exc)
                self.stats.record_error(
                    provider_name, resolved_model, status, self._cooldown_for(exc)
                )
                state.record_failure(exc, cascade.now())
                fallback_used = True
                if provider_name not in failed_providers:
                    failed_providers.add(provider_name)
                    errors.append(exc)
                logger.warning(
                    "[AI-GATEWAY] cascade attempt=%d provider=%s model=%s "
                    "result=failure failure_reason=%s fallback=%s",
                    attempt,
                    provider_name,
                    resolved_model,
                    status,
                    next_label if recoverable else "classic",
                )
                if not recoverable:
                    # Classification courante : erreur non récupérable, la
                    # cascade s'arrête (pas de déroulement aveugle).
                    return None
                continue

            latency = asyncio.get_event_loop().time() - started
            self.stats.record_request(provider_name, resolved_model)
            self.stats.record_success(provider_name, resolved_model, tokens_in, tokens_out)
            if fallback_used:
                self.stats.record_fallback(provider_name)
            logger.info(
                "[AI-GATEWAY] cascade attempt=%d provider=%s model=%s "
                "result=success failure_reason=- fallback=none",
                attempt,
                provider_name,
                resolved_model,
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
            "[AI-GATEWAY] status=cascade_exhausted errors=%s",
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

    def _preferred_name(self, preferred_provider: str | None) -> str:
        """Provider préféré effectif (paramètre d'appel, sinon défaut configuré)."""
        preferred = (preferred_provider or "").strip().lower()
        if not preferred or preferred == "auto":
            default = (self.settings.AI_DEFAULT_PROVIDER or "").strip().lower()
            if default and default != "auto":
                preferred = default
        if preferred and preferred in PROVIDER_NAMES:
            return preferred
        return ""

    def _resolve_order(self, preferred_provider: str | None) -> list[str]:
        order = [p.strip().lower() for p in self.settings.AI_PROVIDER_ORDER.split(",") if p.strip()]
        order = order or list(DEFAULT_PROVIDER_ORDER)
        preferred = self._preferred_name(preferred_provider)
        if preferred:
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
