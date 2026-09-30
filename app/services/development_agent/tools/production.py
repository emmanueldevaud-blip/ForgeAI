"""Outil de déploiement production pour l'Agent Développement."""

from __future__ import annotations

import subprocess
from typing import Any

from app.services.development_agent.tool_registry import ToolContext, ToolSpec


async def deploy_production(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Déploie en production via le script existant (validation utilisateur OBLIGATOIRE)."""
    confirmed = args.get("confirmed", False)
    if not confirmed:
        return {
            "error": "Confirmation requise pour le déploiement production",
            "requires_confirmation": True,
        }

    # Le script de déploiement existant
    deploy_script = "/home/edevaud/deploy-forgeai.sh"

    try:
        result = subprocess.run(
            [deploy_script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutError:
        return {"error": "Timeout déploiement (5 min)"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


PRODUCTION_SPECS = [
    ToolSpec(
        name="deploy_production",
        description="Déploie en production via le script ~/deploy-forgeai.sh (VALIDATION OBLIGATOIRE).",
        input_schema={
            "type": "object",
            "properties": {
                "confirmed": {"type": "boolean", "description": "Confirmation explicite (défaut: false)"},
            },
        },
        handler=deploy_production,
        permission="development.deploy",
        access="write",
        requires_confirmation=True,
    ),
]