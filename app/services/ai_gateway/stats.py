"""Statistiques d'utilisation et suivi des quotas de l'AI Gateway.

Structure minimaliste en mémoire : aucun secret, aucun prompt stocké.
"""

import time
from dataclasses import dataclass


@dataclass
class ProviderStats:
    provider: str
    requests: int = 0
    errors: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    fallbacks: int = 0
    last_used: float | None = None
    status: str = "idle"
    cooldown_until: float = 0.0


@dataclass
class ModelStats:
    provider: str
    model: str
    requests: int = 0
    errors: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    last_used: float | None = None


class StatsStore:
    """Compteurs d'usage par fournisseur et par modèle."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderStats] = {}
        self._models: dict[tuple[str, str], ModelStats] = {}

    def _provider(self, name: str) -> ProviderStats:
        if name not in self._providers:
            self._providers[name] = ProviderStats(provider=name)
        return self._providers[name]

    def _model(self, provider: str, model: str) -> ModelStats:
        key = (provider, model)
        if key not in self._models:
            self._models[key] = ModelStats(provider=provider, model=model)
        return self._models[key]

    def record_request(self, provider: str, model: str) -> None:
        now = time.time()
        stats = self._provider(provider)
        stats.requests += 1
        stats.last_used = now
        stats.status = "ok"
        model_stats = self._model(provider, model)
        model_stats.requests += 1
        model_stats.last_used = now

    def record_success(self, provider: str, model: str, tokens_input: int | None, tokens_output: int | None) -> None:
        stats = self._provider(provider)
        stats.status = "ok"
        stats.cooldown_until = 0.0
        if tokens_input:
            stats.tokens_input += tokens_input
        if tokens_output:
            stats.tokens_output += tokens_output
        model_stats = self._model(provider, model)
        if tokens_input:
            model_stats.tokens_input += tokens_input
        if tokens_output:
            model_stats.tokens_output += tokens_output

    def record_error(self, provider: str, model: str, status: str, cooldown_seconds: float) -> None:
        stats = self._provider(provider)
        stats.errors += 1
        stats.status = status
        stats.last_used = time.time()
        if cooldown_seconds > 0:
            stats.cooldown_until = time.time() + cooldown_seconds
        self._model(provider, model).errors += 1

    def record_fallback(self, provider: str) -> None:
        self._provider(provider).fallbacks += 1

    def is_available(self, provider: str, now: float | None = None) -> bool:
        stats = self._providers.get(provider)
        if stats is None:
            return True
        return (now if now is not None else time.time()) >= stats.cooldown_until

    def snapshot(self) -> dict:
        return {
            "providers": [
                {
                    "provider": s.provider,
                    "requests": s.requests,
                    "errors": s.errors,
                    "tokens_input": s.tokens_input,
                    "tokens_output": s.tokens_output,
                    "fallbacks": s.fallbacks,
                    "last_used": s.last_used,
                    "status": s.status,
                }
                for s in self._providers.values()
            ],
            "models": [
                {
                    "provider": m.provider,
                    "model": m.model,
                    "requests": m.requests,
                    "errors": m.errors,
                    "tokens_input": m.tokens_input,
                    "tokens_output": m.tokens_output,
                    "last_used": m.last_used,
                }
                for m in self._models.values()
            ],
        }

    def quota_status(self) -> dict[str, str]:
        """Statut court par fournisseur (ok / cooldown / inactif)."""
        now = time.time()
        result: dict[str, str] = {}
        for name, stats in self._providers.items():
            if stats.cooldown_until > now:
                result[name] = f"cooldown:{stats.status}"
            else:
                result[name] = stats.status
        return result
