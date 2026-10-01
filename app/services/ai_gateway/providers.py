"""Fournisseurs IA de l'AI Gateway.

Implémentation HTTP directe via httpx (aucun SDK propriétaire), compatible
avec l'API « chat/completions » proposée par Groq, Gemini (endpoint
OpenAI-compatible) et OpenRouter.
"""

import httpx

from app.core.config import Settings, get_settings
from app.services.ai_gateway.errors import (
    AIAuthenticationError,
    AIInvalidResponse,
    AIProviderUnavailable,
    AIQuotaExceeded,
    AIRequestTimeout,
)

DEFAULT_TIMEOUT_SECONDS = 30.0


class BaseAIProvider:
    """Fournisseur OpenAI-compatible : une classe par fournisseur."""

    name: str = ""
    enabled_setting: str = ""
    api_key_setting: str = ""
    base_url_setting: str = ""

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, self.enabled_setting, False))

    @property
    def api_key(self) -> str:
        return getattr(self.settings, self.api_key_setting, "") or ""

    @property
    def base_url(self) -> str:
        return getattr(self.settings, self.base_url_setting, "").rstrip("/")

    @property
    def is_available(self) -> bool:
        """Un fournisseur n'est utilisable que s'il est activé ET configuré."""
        return self.enabled and bool(self.api_key) and bool(self.base_url)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, int | None, int | None]:
        """Appel chat/completions. Retourne (texte, tokens_in, tokens_out)."""
        payload: dict = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Authorization": f"Bearer {self.api_key}"}
        timeout = getattr(self.settings, "AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=timeout)
        try:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
            except httpx.TimeoutException as exc:
                raise AIRequestTimeout(provider=self.name) from exc
            except httpx.HTTPError as exc:
                raise AIProviderUnavailable(
                    f"Erreur réseau avec {self.name}", provider=self.name
                ) from exc
            return self._parse_response(response)
        finally:
            if owns_client:
                await client.aclose()

    def _parse_response(self, response: httpx.Response) -> tuple[str, int | None, int | None]:
        status = response.status_code
        if status in (401, 403):
            raise AIAuthenticationError(provider=self.name)
        if status == 429:
            raise AIQuotaExceeded(provider=self.name)
        if status >= 500:
            raise AIProviderUnavailable(
                f"Erreur serveur {status} depuis {self.name}", provider=self.name
            )
        if status >= 400:
            raise AIProviderUnavailable(
                f"Rejeté par {self.name} (HTTP {status})", provider=self.name, retryable=False
            )

        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise AIInvalidResponse(provider=self.name)
        except AIInvalidResponse:
            raise
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIInvalidResponse(provider=self.name) from exc

        usage = body.get("usage") or {}
        tokens_input = usage.get("prompt_tokens")
        tokens_output = usage.get("completion_tokens")
        return text, tokens_input, tokens_output


class GroqProvider(BaseAIProvider):
    name = "groq"
    enabled_setting = "GROQ_ENABLED"
    api_key_setting = "GROQ_API_KEY"
    base_url_setting = "GROQ_BASE_URL"


class GeminiProvider(BaseAIProvider):
    name = "gemini"
    enabled_setting = "GEMINI_ENABLED"
    api_key_setting = "GEMINI_API_KEY"
    base_url_setting = "GEMINI_BASE_URL"


class OpenRouterProvider(BaseAIProvider):
    name = "openrouter"
    enabled_setting = "OPENROUTER_ENABLED"
    api_key_setting = "OPENROUTER_API_KEY"
    base_url_setting = "OPENROUTER_BASE_URL"


class OpenCodeProvider(BaseAIProvider):
    """Modèles OpenCode (CLI local), notamment les modèles gratuits.

    Pas de clé API ni d'URL : l'appel se fait via ``opencode run``.
    """

    name = "opencode"

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "OPENCODE_ENABLED", True))

    @property
    def is_available(self) -> bool:
        if not self.enabled:
            return False
        return self._opencode().is_available()

    def _opencode(self):
        from app.services.development_agent.opencode import OpenCodeClient

        if getattr(self, "_opencode_client", None) is None:
            self._opencode_client = OpenCodeClient(self.settings)
        return self._opencode_client

    @staticmethod
    def _prompt_from_messages(messages: list[dict[str, str]]) -> str:
        parts: list[str] = []
        for message in messages:
            role = (message.get("role") or "user").lower()
            content = message.get("content") or ""
            if not content:
                continue
            if role == "system":
                parts.append(content)
            elif role == "assistant":
                parts.append(f"Assistant : {content}")
            else:
                parts.append(f"Utilisateur : {content}")
        return "\n\n".join(parts)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, int | None, int | None]:
        client = self._opencode()
        if not client.is_available():
            raise AIProviderUnavailable("OpenCode non disponible", provider=self.name)

        prompt = self._prompt_from_messages(messages)
        if not prompt:
            raise AIProviderUnavailable("Prompt vide", provider=self.name)

        model_id = model if model.startswith("opencode/") else f"opencode/{model}"
        timeout = getattr(self.settings, "AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        try:
            timeout_seconds = int(float(timeout) or DEFAULT_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            timeout_seconds = int(DEFAULT_TIMEOUT_SECONDS)

        result = await client.run_task(prompt, model=model_id, timeout=timeout_seconds)
        if result.success:
            text = (result.output or "").strip()
            if not text:
                raise AIProviderUnavailable(
                    "Réponse vide d'OpenCode", provider=self.name
                )
            return text, None, None

        error_text = f"{result.error or ''} {result.output or ''}".lower()
        if "timeout" in error_text:
            raise AIRequestTimeout(provider=self.name)
        if "rate limit" in error_text or "429" in error_text or "quota" in error_text:
            raise AIQuotaExceeded(provider=self.name)
        raise AIProviderUnavailable(
            f"OpenCode: {result.error or 'échec de l’appel'}", provider=self.name
        )


PROVIDER_CLASSES: dict[str, type[BaseAIProvider]] = {
    "opencode": OpenCodeProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
}


def build_providers(
    settings: Settings | None = None, client: httpx.AsyncClient | None = None
) -> dict[str, BaseAIProvider]:
    resolved = settings or get_settings()
    return {name: cls(resolved, client) for name, cls in PROVIDER_CLASSES.items()}
