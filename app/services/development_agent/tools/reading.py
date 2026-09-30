"""Outils de lecture pour l'Agent Développement."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.models import DevelopmentTask
from app.services.development_agent.tool_registry import ToolContext, ToolSpec


async def get_repository_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """État du repository Git : branche, status, commits récents."""
    work_dir = Path(ctx.work_dir)
    try:
        # Branche courante
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = branch_result.stdout.strip() or "detached"

        # Status
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        status_lines = status_result.stdout.strip().splitlines()
        modified = [line[3:] for line in status_lines if line.startswith(" M") or line.startswith("M ")]
        added = [line[3:] for line in status_lines if line.startswith("A ")]
        deleted = [line[3:] for line in status_lines if line.startswith(" D")]
        untracked = [line[3:] for line in status_lines if line.startswith("??")]

        # Derniers commits
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        commits = [line for line in log_result.stdout.strip().splitlines() if line]

        return {
            "branch": branch,
            "modified": modified,
            "added": added,
            "deleted": deleted,
            "untracked": untracked,
            "recent_commits": commits,
            "clean": len(status_lines) == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout git"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


async def read_file(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Lit un fichier du repository."""
    path = args.get("path")
    if not path:
        return {"error": "Chemin requis"}

    # Sécurité : éviter la traversée de répertoire
    try:
        work_dir = Path(ctx.work_dir).resolve()
        target = (work_dir / path).resolve()
        if not target.is_relative_to(work_dir):
            return {"error": "Accès refusé : hors du repository"}
    except Exception:
        return {"error": "Chemin invalide"}

    if not target.exists():
        return {"error": "Fichier non trouvé"}
    if not target.is_file():
        return {"error": "Ce n'est pas un fichier"}

    try:
        content = target.read_text(encoding="utf-8")
        return {"path": path, "content": content, "size": len(content)}
    except UnicodeDecodeError:
        return {"error": "Fichier binaire ou encodage non supporté"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


async def search_code(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Recherche un pattern dans le code (grep)."""
    pattern = args.get("pattern")
    if not pattern:
        return {"error": "Pattern requis"}

    include = args.get("include", "")
    exclude = args.get("exclude", "")

    work_dir = Path(ctx.work_dir)
    cmd = ["grep", "-r", "-n", pattern, "."]
    if include:
        cmd.extend(["--include", include])
    if exclude:
        cmd.extend(["--exclude", exclude])

    try:
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = result.stdout.strip().splitlines()
        matches = []
        for line in lines[:100]:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                matches.append({"file": parts[0], "line": int(parts[1]), "content": parts[2]})
        return {"matches": matches, "total": len(lines), "truncated": len(lines) > 100}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout recherche"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


async def list_files(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Liste les fichiers du repository (arborescence)."""
    path = args.get("path", ".")
    max_depth = args.get("max_depth", 3)

    work_dir = Path(ctx.work_dir).resolve()
    target = (work_dir / path).resolve()
    if not target.is_relative_to(work_dir):
        return {"error": "Accès refusé"}

    if not target.exists():
        return {"error": "Chemin non trouvé"}

    def walk(dir_path: Path, depth: int = 0) -> list[dict[str, Any]]:
        if depth > max_depth:
            return []
        items = []
        try:
            for entry in sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.name.startswith(".") and entry.name not in (".gitignore", ".env.example"):
                    continue
                item = {"name": entry.name, "path": str(entry.relative_to(work_dir)), "is_dir": entry.is_dir()}
                if entry.is_dir():
                    item["children"] = walk(entry, depth + 1)
                items.append(item)
        except PermissionError:
            pass
        return items

    return {"root": path, "tree": walk(target)}


async def get_git_diff(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Obtient le diff Git (working tree vs HEAD ou entre commits)."""
    work_dir = Path(ctx.work_dir)
    staged = args.get("staged", False)
    commit = args.get("commit")

    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if commit:
            cmd.append(commit)

        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {"diff": result.stdout, "staged": staged}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout diff"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


# Spécifications pour le registre
READ_SPECS = [
    ToolSpec(
        name="get_repository_status",
        description="État du repository Git : branche, status, commits récents.",
        input_schema={"type": "object", "properties": {}},
        handler=get_repository_status,
        permission="development.read",
        access="read",
    ),
    ToolSpec(
        name="read_file",
        description="Lit un fichier du repository.",
        input_schema={"type": "object", "properties": {"path": {"type": "string", "description": "Chemin relatif au repository"}}, "required": ["path"]},
        handler=read_file,
        permission="development.read",
        access="read",
    ),
    ToolSpec(
        name="search_code",
        description="Recherche un pattern dans le code (grep).",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Pattern à rechercher"},
                "include": {"type": "string", "description": "Filtre --include (ex: *.py)"},
                "exclude": {"type": "string", "description": "Filtre --exclude"},
            },
            "required": ["pattern"],
        },
        handler=search_code,
        permission="development.read",
        access="read",
    ),
    ToolSpec(
        name="list_files",
        description="Liste l'arborescence des fichiers.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin de départ (défaut: .)"},
                "max_depth": {"type": "integer", "description": "Profondeur max (défaut: 3)"},
            },
        },
        handler=list_files,
        permission="development.read",
        access="read",
    ),
    ToolSpec(
        name="get_git_diff",
        description="Obtient le diff Git (working tree vs HEAD ou entre commits).",
        input_schema={
            "type": "object",
            "properties": {
                "staged": {"type": "boolean", "description": "Diff staged (défaut: false)"},
                "commit": {"type": "string", "description": "Commit de référence (optionnel)"},
            },
        },
        handler=get_git_diff,
        permission="development.read",
        access="read",
    ),
]