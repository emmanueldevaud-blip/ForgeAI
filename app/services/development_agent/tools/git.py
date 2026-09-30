"""Outils Git pour l'Agent Développement."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from app.services.development_agent.tool_registry import ToolContext, ToolSpec


async def create_commit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Crée un commit avec les modifications actuelles."""
    message = args.get("message")
    if not message:
        return {"error": "Message de commit requis"}

    add_all = args.get("add_all", True)
    work_dir = Path(ctx.work_dir)

    try:
        if add_all:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=work_dir,
                check=True,
                capture_output=True,
                timeout=10,
            )

        # Vérifier s'il y a quelque chose à commiter
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=work_dir,
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            return {"error": "Aucune modification à commiter"}

        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"error": f"Commit échoué: {result.stderr}"}

        # Récupérer le hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work_dir,
            capture_output=True,
            text=True,
        )
        commit_hash = hash_result.stdout.strip()

        return {
            "success": True,
            "commit_hash": commit_hash,
            "message": message,
            "output": result.stdout,
        }
    except subprocess.CalledProcessError as exc:
        return {"error": f"Git error: {exc.stderr}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


async def push_branch(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Pousse la branche courante vers le remote."""
    remote = args.get("remote", "origin")
    force = args.get("force", False)
    work_dir = Path(ctx.work_dir)

    try:
        # Branche courante
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=work_dir,
            capture_output=True,
            text=True,
        )
        branch = branch_result.stdout.strip()
        if not branch or branch == "detached":
            return {"error": "Aucune branche courante"}

        cmd = ["git", "push", remote, branch]
        if force:
            cmd.append("--force-with-lease")

        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {"error": f"Push échoué: {result.stderr}"}

        return {
            "success": True,
            "branch": branch,
            "remote": remote,
            "output": result.stdout,
        }
    except subprocess.CalledProcessError as exc:
        return {"error": f"Git error: {exc.stderr}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


async def create_branch(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Crée une nouvelle branche."""
    name = args.get("name")
    if not name:
        return {"error": "Nom de branche requis"}

    base = args.get("base")
    work_dir = Path(ctx.work_dir)

    try:
        cmd = ["git", "checkout", "-b", name]
        if base:
            cmd.append(base)

        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"error": f"Création branche échouée: {result.stderr}"}

        return {"success": True, "branch": name, "base": base or "HEAD"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


GIT_SPECS = [
    ToolSpec(
        name="create_commit",
        description="Crée un commit avec les modifications actuelles (validation utilisateur requise).",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message de commit"},
                "add_all": {"type": "boolean", "description": "Ajouter toutes les modifications (défaut: true)"},
            },
            "required": ["message"],
        },
        handler=create_commit,
        permission="development.commit",
        access="write",
        requires_confirmation=True,
    ),
    ToolSpec(
        name="push_branch",
        description="Pousse la branche courante vers le remote (validation utilisateur requise).",
        input_schema={
            "type": "object",
            "properties": {
                "remote": {"type": "string", "description": "Remote Git (défaut: origin)"},
                "force": {"type": "boolean", "description": "Force push avec lease (défaut: false)"},
            },
        },
        handler=push_branch,
        permission="development.push",
        access="write",
        requires_confirmation=True,
    ),
    ToolSpec(
        name="create_branch",
        description="Crée une nouvelle branche de développement.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom de la branche"},
                "base": {"type": "string", "description": "Branche de base (optionnel)"},
            },
            "required": ["name"],
        },
        handler=create_branch,
        permission="development.execute",
        access="write",
    ),
]