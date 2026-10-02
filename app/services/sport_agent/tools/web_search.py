"""Outil de recherche Web pour l'Agent Sport.

Permet à l'agent de rechercher des informations externes (entraînement, trail,
nutrition, récupération, matériel, courses, etc.) de manière autonome.

Architecture multi-provider avec fallback :
- Brave Search (si clé API configurée)
- DuckDuckGo (gratuit, sans clé, fallback par défaut)
- Serper/Google (si clé API configurée)

Cache simple en mémoire pour éviter les requêtes identiques.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx
from lxml import html

from app.core.config import get_settings
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    published_date: str | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "published_date": self.published_date,
            "retrieved_at": self.retrieved_at,
            "provider": self.provider,
        }


class WebSearchError(Exception):
    """Erreur lors de la recherche Web."""

    pass


class _SearchCache:
    """Cache simple en mémoire pour les résultats de recherche."""

    def __init__(self, enabled: bool = True, ttl_seconds: int = 3600):
        self.enabled = enabled
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[list[SearchResult], float]] = {}

    def _make_key(self, provider: str, query: str, max_results: int) -> str:
        import hashlib
        key_str = f"{provider}:{query}:{max_results}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, provider: str, query: str, max_results: int) -> list[SearchResult] | None:
        if not self.enabled:
            return None
        key = self._make_key(provider, query, max_results)
        if key in self._cache:
            results, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                logger.debug("[SPORT-AGENT] event=web_search_cache_hit provider=%s query=%s", provider, query[:80])
                return results
            else:
                del self._cache[key]
        return None

    def set(self, provider: str, query: str, max_results: int, results: list[SearchResult]) -> None:
        if not self.enabled:
            return
        key = self._make_key(provider, query, max_results)
        self._cache[key] = (results, time.time())
        logger.debug("[SPORT-AGENT] event=web_search_cache_set provider=%s query=%s", provider, query[:80])

    def clear(self) -> None:
        self._cache.clear()


class WebSearchProvider:
    """Provider de recherche Web avec support multi-moteurs et fallback automatique."""

    PROVIDER_ORDER = ["brave", "duckduckgo", "serper"]

    def __init__(self, settings: Any | None = None):
        self.settings = settings or get_settings()
        self.primary_provider = self.settings.WEB_SEARCH_PROVIDER.lower()
        self.api_key = self.settings.WEB_SEARCH_API_KEY
        self.max_results = self.settings.WEB_SEARCH_MAX_RESULTS
        self.timeout = self.settings.WEB_SEARCH_TIMEOUT_SECONDS
        self.fallback_enabled = self.settings.WEB_SEARCH_FALLBACK_ENABLED
        self._client: httpx.AsyncClient | None = None
        self._cache = _SearchCache(
            enabled=self.settings.WEB_SEARCH_CACHE_ENABLED,
            ttl_seconds=self.settings.WEB_SEARCH_CACHE_TTL_SECONDS,
        )

    def _get_provider_order(self) -> list[str]:
        """Retourne l'ordre des providers à essayer selon la config."""
        if self.primary_provider == "duckduckgo":
            return ["duckduckgo"]
        if self.primary_provider == "serper":
            return ["serper"]
        if self.primary_provider == "brave":
            order = ["brave"]
            if self.fallback_enabled:
                order.append("duckduckgo")
            return order
        return ["duckduckgo"]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _clean_snippet(self, text: str) -> str:
        """Nettoie un extrait de texte."""
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[\x00-\x1f\x7f]", "", text)
        return text.strip()[:400]

    async def _search_duckduckgo(self, query: str) -> list[SearchResult]:
        """Recherche via DuckDuckGo HTML (gratuit, sans clé API)."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        client = await self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()

        doc = html.fromstring(resp.text)
        results: list[SearchResult] = []

        for result in doc.cssselect(".result__body")[: self.max_results]:
            title_el = result.cssselect(".result__title a")
            snippet_el = result.cssselect(".result__snippet")
            url_el = result.cssselect(".result__url")

            title = title_el[0].text_content().strip() if title_el else ""
            snippet = snippet_el[0].text_content().strip() if snippet_el else ""
            url = url_el[0].text_content().strip() if url_el else ""
            link = title_el[0].get("href", "") if title_el else ""

            if not title or not link:
                continue

            if link.startswith("//duckduckgo.com/l/?uddg="):
                import urllib.parse
                link = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])

            results.append(
                SearchResult(
                    title=self._clean_snippet(title),
                    url=link,
                    snippet=self._clean_snippet(snippet),
                    source="DuckDuckGo",
                    provider="duckduckgo",
                )
            )

        return results

    async def _search_brave(self, query: str) -> list[SearchResult]:
        """Recherche via Brave Search API (nécessite clé API)."""
        if not self.api_key:
            raise WebSearchError("Clé API Brave Search manquante")

        url = "https://api.search.brave.com/res/v1/web/search"
        params = {"q": query, "count": min(self.max_results, 20), "lang": "fr", "country": "FR"}
        headers = {"Accept": "application/json", "X-Subscription-Token": self.api_key}

        client = await self._get_client()
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("web", {}).get("results", [])[: self.max_results]:
            results.append(
                SearchResult(
                    title=self._clean_snippet(item.get("title", "")),
                    url=item.get("url", ""),
                    snippet=self._clean_snippet(item.get("description", "")),
                    source="Brave",
                    provider="brave",
                    published_date=item.get("age") or item.get("published"),
                )
            )
        return results

    async def _search_serper(self, query: str) -> list[SearchResult]:
        """Recherche via Serper API (Google Search, nécessite clé API)."""
        if not self.api_key:
            raise WebSearchError("Clé API Serper manquante")

        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": min(self.max_results, 100), "gl": "fr", "hl": "fr"}
        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}

        client = await self._get_client()
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("organic", [])[: self.max_results]:
            results.append(
                SearchResult(
                    title=self._clean_snippet(item.get("title", "")),
                    url=item.get("link", ""),
                    snippet=self._clean_snippet(item.get("snippet", "")),
                    source="Google (Serper)",
                    provider="serper",
                    published_date=item.get("date"),
                )
            )
        return results

    async def _search_with_provider(self, provider: str, query: str) -> list[SearchResult]:
        """Effectue la recherche avec un provider spécifique."""
        if provider == "brave":
            return await self._search_brave(query)
        elif provider == "serper":
            return await self._search_serper(query)
        else:
            return await self._search_duckduckgo(query)

    async def search(self, query: str, max_results: int | None = None) -> list[SearchResult]:
        """Effectue une recherche Web avec fallback automatique."""
        if not self.settings.WEB_SEARCH_ENABLED:
            raise WebSearchError("Recherche Web désactivée")

        if not query or not query.strip():
            raise WebSearchError("Requête vide")

        max_results = max_results or self.max_results
        old_max = self.max_results
        self.max_results = min(max_results, old_max)

        provider_order = self._get_provider_order()
        last_error: Exception | None = None

        for provider in provider_order:
            try:
                # Vérifier le cache
                cached = self._cache.get(provider, query, max_results)
                if cached is not None:
                    logger.info(
                        "[SPORT-AGENT] event=web_search_cache_hit provider=%s query=%s",
                        provider,
                        query[:80],
                    )
                    for r in cached:
                        r.provider = provider  # Marquer le provider réellement utilisé
                    return cached

                logger.info(
                    "[SPORT-AGENT] event=web_search provider=%s query=%s",
                    provider,
                    query[:80],
                )
                started = time.monotonic()

                results = await self._search_with_provider(provider, query)

                duration_ms = int((time.monotonic() - started) * 1000)
                logger.info(
                    "[SPORT-AGENT] event=web_search_done provider=%s results=%d duration_ms=%d",
                    provider,
                    len(results),
                    duration_ms,
                )

                # Mettre en cache
                self._cache.set(provider, query, max_results, results)

                for r in results:
                    r.provider = provider
                return results

            except httpx.TimeoutException:
                last_error = WebSearchError(f"Timeout ({self.timeout}s)")
                logger.warning(
                    "[SPORT-AGENT] event=web_search_timeout provider=%s query=%s",
                    provider,
                    query[:80],
                )
            except httpx.HTTPStatusError as exc:
                last_error = WebSearchError(f"Erreur HTTP {exc.response.status_code}")
                logger.warning(
                    "[SPORT-AGENT] event=web_search_http_error provider=%s status=%d query=%s",
                    provider,
                    exc.response.status_code,
                    query[:80],
                )
            except WebSearchError as exc:
                last_error = exc
                logger.warning(
                    "[SPORT-AGENT] event=web_search_error provider=%s query=%s error=%s",
                    provider,
                    query[:80],
                    exc,
                )
            except Exception as exc:
                last_error = WebSearchError(f"{type(exc).__name__}: {exc}")
                logger.exception("[SPORT-AGENT] event=web_search_exception provider=%s", provider)

            # Si fallback activé, on essaie le provider suivant
            if self.fallback_enabled and provider != provider_order[-1]:
                logger.info(
                    "[SPORT-AGENT] event=web_search_fallback from=%s to=%s",
                    provider,
                    provider_order[provider_order.index(provider) + 1],
                )
                continue
            else:
                break

        # Tous les providers ont échoué
        raise WebSearchError(f"Tous les providers ont échoué: {last_error}") from last_error


async def web_search(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Recherche d'informations sur Internet pour enrichir l'analyse sportive.

    L'outil permet à l'agent de trouver des informations externes utiles :
    - entraînement, trail, ultra-trail, course à pied
    - récupération, sommeil, nutrition, hydratation
    - physiologie de l'effort, recherche scientifique
    - matériel sportif, chaussures, montres GPS
    - événements, courses, parcours, ravitaillements
    - actualités sportives, recommandations récentes

    Args:
        query: Requête de recherche (ex: "effets chaleur fréquence cardiaque trail")
        max_results: Nombre max de résultats (défaut 8, max 15)
        objective: Objectif de recherche optionnel pour guider le tri
    """
    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query_requise"}

    max_results = args.get("max_results")
    objective = args.get("objective")

    if max_results is not None:
        try:
            max_results = int(max_results)
        except (TypeError, ValueError):
            max_results = None

    try:
        provider = WebSearchProvider()
        results = await provider.search(query, max_results)
        await provider.close()

        if not results:
            return {"ok": True, "results": [], "query": query, "note": "aucun_resultat"}

        if objective:
            logger.info(
                "[SPORT-AGENT] event=web_search_objective objective=%s", objective[:80]
            )

        return {
            "ok": True,
            "query": query,
            "results": [r.as_dict() for r in results],
            "count": len(results),
            "provider": results[0].provider if results else None,
        }

    except WebSearchError as exc:
        logger.warning("[SPORT-AGENT] event=web_search_error query=%s error=%s", query[:80], exc)
        return {"ok": False, "error": f"recherche_echouee: {exc}"}
    except Exception as exc:
        logger.exception("[SPORT-AGENT] event=web_search_exception query=%s", query[:80])
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="web_search",
        description=(
            "Recherche d'informations sur Internet pour le coaching sportif. "
            "Utilise cet outil quand les données ForgeAI (Garmin, historique, objectifs) "
            "ne suffisent pas pour répondre. Exemples : effets chaleur FC, stratégie "
            "nutrition ultra-trail, dérive cardiaque, caractéristiques chaussures, "
            "règlement course, actualités trail. L'outil retourne titre, URL, extrait, "
            "source et date. Privilégie les sources officielles/scientifiques. "
            "Supporte multi-provider avec fallback automatique (Brave → DuckDuckGo)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Requête de recherche en langage naturel (français ou anglais)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Nombre max de résultats (défaut 8, max 15)",
                    "minimum": 1,
                    "maximum": 15,
                },
                "objective": {
                    "type": "string",
                    "description": "Objectif de la recherche pour guider l'analyse (ex: 'comprendre dérive cardiaque')",
                },
            },
            "required": ["query"],
        },
        handler=web_search,
        permission="sport.access",
        access="read",
    ),
]