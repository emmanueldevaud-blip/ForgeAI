"""Erreurs normalisées de l'AI Gateway ForgeAI.

Les erreurs spécifiques Groq / Gemini / OpenRouter sont traduites en ces
exceptions afin que les modules applicatifs n'aient jamais à connaître un
fournisseur en particulier.
"""


class AIGatewayError(Exception):
    """Base de toutes les erreurs de la passerelle."""

    def __init__(self, message: str = "", provider: str | None = None, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class AIProviderUnavailable(AIGatewayError):
    """Fournisseur temporairement indisponible (réseau, 5xx, service down)."""

    def __init__(self, message: str = "Fournisseur IA indisponible", provider: str | None = None, retryable: bool = True):
        super().__init__(message, provider=provider, retryable=retryable)


class AIQuotaExceeded(AIGatewayError):
    """Quota ou rate limit atteint (HTTP 429)."""

    def __init__(self, message: str = "Quota ou rate limit atteint", provider: str | None = None):
        super().__init__(message, provider=provider, retryable=True)


class AIAuthenticationError(AIGatewayError):
    """Clé API absente, invalide ou refusée (HTTP 401/403)."""

    def __init__(self, message: str = "Authentification fournisseur invalide", provider: str | None = None):
        super().__init__(message, provider=provider, retryable=False)


class AIRequestTimeout(AIGatewayError):
    """Délai dépassé lors de l'appel au fournisseur."""

    def __init__(self, message: str = "Délai dépassé", provider: str | None = None):
        super().__init__(message, provider=provider, retryable=True)


class AIInvalidResponse(AIGatewayError):
    """Réponse du fournisseur illisible ou incomplète."""

    def __init__(self, message: str = "Réponse IA invalide", provider: str | None = None):
        super().__init__(message, provider=provider, retryable=False)


class AINoProviderAvailable(AIGatewayError):
    """Aucun fournisseur configuré et disponible n'a pu répondre."""

    def __init__(self, message: str = "Aucun fournisseur IA disponible", errors: list[Exception] | None = None):
        super().__init__(message, provider=None, retryable=False)
        self.errors = errors or []
