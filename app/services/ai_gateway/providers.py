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


PROVIDER_CLASSES: dict[str, type[BaseAIProvider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
}


def build_providers(
    settings: Settings | None = None, client: httpx.AsyncClient | None = None
) -> dict[str, BaseAIProvider]:
    resolved = settings or get_settings()
    return {name: cls(resolved, client) for name, cls in PROVIDER_CLASSES.items()}
