"""AI Gateway centralisée de ForgeAI.

Usage :

    from app.services.ai_gateway import ai_gateway

    response = await ai_gateway.generate(
        prompt="Analyse cette demande",
        task_type="general",
    )
    print(response.text, response.provider_used)
"""

from app.services.ai_gateway.errors import (
    AIAuthenticationError,
    AIGatewayError,
    AIInvalidResponse,
    AINoProviderAvailable,
    AIProviderUnavailable,
    AIQuotaExceeded,
    AIRequestTimeout,
)
from app.services.ai_gateway.gateway import AIGateway, AIResponse, ai_gateway, get_ai_gateway
from app.services.ai_gateway.stats import StatsStore

__all__ = [
    "AIAuthenticationError",
    "AIGateway",
    "AIGatewayError",
    "AIInvalidResponse",
    "AINoProviderAvailable",
    "AIProviderUnavailable",
    "AIQuotaExceeded",
    "AIRequestTimeout",
    "AIResponse",
    "StatsStore",
    "ai_gateway",
    "get_ai_gateway",
]
