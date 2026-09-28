"""Client HTTP du Raspberry Pi (passerelle du sechoir).

Contrat d'API attendu sur le Raspberry (documente) :

  GET  {base_url}/state
       -> {"temperature": 14.2, "humidity": 80.0,
           "weight": 742.0,          # optionnel (pas de balance => absent)
           "outputs": [0,1,0,0,0,0,0,0],   # 8 sorties GPIO
           "timestamp": "ISO8601"}   # optionnel
  POST {base_url}/command
       body: {"index": 0, "state": true}  -> 2xx
  GET  {base_url}/health -> {"ok": true}  # test de connexion (fallback /state)

Le Raspberry reste une passerelle pure : aucune logique de sechage n'y est
placee par ForgeAI. Les securites materielles locales du Raspberry ne sont
jamais modifiees par ce client.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 6.0
OUTPUT_COUNT = 8


class RaspberryError(Exception):
    """Erreur de communication avec le Raspberry."""


def credentials_from_config(config: dict[str, Any] | None) -> tuple[str, str] | None:
    """Retourne les identifiants Basic Auth (utilisateur, mot de passe) s'il y en a."""
    cfg = config or {}
    user = cfg.get("api_user")
    password = cfg.get("api_password")
    if user and password:
        return (str(user), str(password))
    return None


def _normalize_outputs(raw: Any) -> list[bool]:
    outputs: list[bool] = [False] * OUTPUT_COUNT
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                outputs[int(key)] = bool(value)
            except (TypeError, ValueError):
                continue
    elif isinstance(raw, (list, tuple)):
        for i, value in enumerate(raw[:OUTPUT_COUNT]):
            outputs[i] = bool(value)
    return outputs


def _normalize_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return round(value, 3)


def normalize_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise la reponse /state vers le format interne ForgeAI."""
    timestamp = None
    raw_ts = payload.get("timestamp") or payload.get("ts")
    if raw_ts:
        try:
            timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            timestamp = None
    return {
        "temperature": _normalize_float(payload.get("temperature")),
        "humidity": _normalize_float(payload.get("humidity")),
        "weight": _normalize_float(payload.get("weight")),
        "outputs": _normalize_outputs(payload.get("outputs")),
        "timestamp": timestamp,
    }


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    auth: tuple[str, str] | None = None,
) -> dict[str, Any]:
    try:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise RaspberryError("Authentification refusee (identifiants incorrects)") from exc
        raise RaspberryError(f"HTTP {exc.response.status_code} sur {url}") from exc
    except httpx.TimeoutException as exc:
        raise RaspberryError(f"Delai depasse sur {url}") from exc
    except ValueError as exc:
        raise RaspberryError(f"Reponse JSON invalide sur {url}") from exc
    except httpx.HTTPError as exc:
        raise RaspberryError(f"Erreur reseau sur {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise RaspberryError(f"Reponse inattendue sur {url}")
    return data


async def fetch_state(
    base_url: str,
    timeout: float = _TIMEOUT_SECONDS,
    auth: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Recupere l'etat courant (capteurs + sorties) du Raspberry."""
    if not base_url:
        raise RaspberryError("Adresse du Raspberry non configuree")
    url = f"{base_url.rstrip('/')}/state"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        payload = await _get_json(client, url, auth=auth)
    state = normalize_state(payload)
    if state["temperature"] is None and state["humidity"] is None:
        raise RaspberryError("Reponse /state sans temperature ni humidite")
    return state


async def send_command(
    base_url: str,
    index: int,
    state: bool,
    timeout: float = _TIMEOUT_SECONDS,
    auth: tuple[str, str] | None = None,
) -> None:
    """Envoie une commande d'equipement (sortie GPIO 0..7) au Raspberry."""
    if not base_url:
        raise RaspberryError("Adresse du Raspberry non configuree")
    if not 0 <= index < OUTPUT_COUNT:
        raise RaspberryError(f"Index de sortie invalide: {index}")
    url = f"{base_url.rstrip('/')}/command"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        try:
            response = await client.post(
                url, json={"index": index, "state": bool(state)}, auth=auth
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise RaspberryError("Authentification refusee (identifiants incorrects)") from exc
            raise RaspberryError(f"HTTP {exc.response.status_code} sur {url}") from exc
        except httpx.TimeoutException as exc:
            raise RaspberryError(f"Delai depasse sur {url}") from exc
        except httpx.HTTPError as exc:
            raise RaspberryError(f"Erreur reseau sur {url}: {exc}") from exc


async def test_connection(
    base_url: str,
    timeout: float = _TIMEOUT_SECONDS,
    auth: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Teste la connexion : GET /health puis fallback GET /state."""
    if not base_url:
        raise RaspberryError("Adresse du Raspberry non configuree")
    started = time.monotonic()
    state: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        try:
            payload = await _get_json(client, f"{base_url.rstrip('/')}/health", auth=auth)
            if not payload.get("ok", True):
                raise RaspberryError("Le Raspberry repond /health: ok=false")
        except RaspberryError:
            state = normalize_state(
                await _get_json(client, f"{base_url.rstrip('/')}/state", auth=auth)
            )
    latency_ms = int((time.monotonic() - started) * 1000)
    return {"latency_ms": latency_ms, "state": state}
