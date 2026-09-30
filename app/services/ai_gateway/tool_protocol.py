"""Protocole d'appel d'outils compatible avec tous les fournisseurs IA.

L'AI Gateway communique avec des fournisseurs OpenAI-compatibles (Groq,
Gemini, OpenRouter) via de simples messages texte. Plutôt que d'ajouter une
dépendance au tool-calling natif de chaque fournisseur, ce module définit un
protocole JSON posé dans le message système :

* le modèle répond ``{"tool_calls": [{"name": ..., "arguments": {...}}]}``
  pour demander l'exécution d'un ou plusieurs outils ;
* il répond ``{"final": <données>}`` lorsqu'il a terminé sa réflexion.

La passerelle exécute les outils, leur résultat repart vers le modèle, et
ainsi de suite jusqu'à la décision finale. Aucun fournisseur, aucun appel IA
existant n'est modifié : le protocole n'est activé que lorsque des outils
sont fournis.
"""

from __future__ import annotations

import json
from typing import Any

MAX_TOOL_INSTRUCTIONS_CHARS = 6000


def build_tool_instructions(tools: list[dict[str, Any]]) -> str:
    """Instructions de protocole ajoutées au message système."""
    catalogue = []
    for tool in tools:
        entry = {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "input_schema": tool.get("input_schema") or {"type": "object", "properties": {}},
            "access": tool.get("access", "read"),
        }
        catalogue.append(entry)
    serialized = json.dumps(catalogue, ensure_ascii=False, default=str)
    if len(serialized) > MAX_TOOL_INSTRUCTIONS_CHARS:
        serialized = serialized[:MAX_TOOL_INSTRUCTIONS_CHARS] + "…"
    return (
        "\n\nOUTILS DISPONIBLES (JSON) :\n"
        f"{serialized}\n\n"
        "PROTOCOLE D'OUTILS — règles absolues :\n"
        "- Tu peux appeler UN OU PLUSIEURS outils pour obtenir les données dont tu as besoin.\n"
        "- Réponds UNIQUEMENT par un objet JSON valide, sans texte avant/après, sans Markdown.\n"
        "- Pour demander des données : "
        '{"tool_calls": [{"name": "nom_outil", "arguments": {...}}]} '
        "(une seule requête par appel, plusieurs outils possibles dans un même tableau).\n"
        "- Pour conclure (décision finale) : {\"final\": {...}} avec le schéma demandé dans ta mission.\n"
        "- N'invente AUCUNE donnée : si tu as besoin d'une information, appelle l'outil correspondant.\n"
        "- N'appelle un outil que s'il est réellement nécessaire à ta mission."
    )


def _loads(text: str) -> Any:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extrait les appels d'outils d'une réponse modèle (liste vide sinon)."""
    payload = _loads(text)
    if not isinstance(payload, dict):
        return []
    raw_calls = payload.get("tool_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in raw_calls:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        arguments = item.get("arguments", item.get("input", {}))
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}
        calls.append({"name": name.strip(), "arguments": arguments})
    return calls


def extract_final_text(text: str) -> str:
    """Texte final : contenu de ``final`` s'il existe, sinon la réponse brute."""
    payload = _loads(text)
    if isinstance(payload, dict) and "final" in payload:
        final = payload.get("final")
        if isinstance(final, str):
            return final
        try:
            return json.dumps(final, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(final)
    return (text or "").strip()


def parse_final(text: str) -> dict[str, Any] | None:
    """Décode une décision finale JSON, ou ``None`` si ce n'est pas un objet."""
    payload = _loads(text)
    if isinstance(payload, dict) and "final" in payload:
        payload = payload.get("final")
    if isinstance(payload, dict):
        return payload
    return None
