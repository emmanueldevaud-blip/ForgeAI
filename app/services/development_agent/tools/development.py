"""Outils de développement pour l'Agent Développement."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.services.development_agent.tool_registry import ToolContext, ToolSpec
from app.services.development_agent.opencode import OpenCodeClient, get_opencode_client


async def start_development_task(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Initialise une tâche de développement : crée la branche, prépare l'environnement."""
    task = ctx.task
    work_dir = Path(ctx.work_dir)

    # Créer une branche de développement si pas déjà sur une branche de tâche
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=work_dir,
        capture_output=True,
        text=True,
    ).stdout.strip()

    if not current_branch.startswith("dev/agent/"):
        branch_name = f"dev/agent/{task.id[:8]}"
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"error": f"Impossible de créer la branche: {result.stderr}"}
        task.branch = branch_name
    else:
        branch_name = current_branch
        task.branch = current_branch

    return {
        "branch": branch_name,
        "message": f"Branche de développement prête: {branch_name}",
        "work_dir": str(work_dir),
    }


async def ask_opencode(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Envoie une instruction à OpenCode et récupère le résultat."""
    prompt = args.get("prompt")
    if not prompt:
        return {"error": "Prompt requis"}

    session_id = args.get("session_id")
    continue_session = args.get("continue", True)
    model = args.get("model")
    agent_name = args.get("agent")

    client = get_opencode_client(ctx.settings)
    if not client.is_available():
        return {"error": "OpenCode non disponible"}

    # Construire le prompt complet avec le contexte
    full_prompt = _build_opencode_prompt(ctx, prompt)

    result = await client.run_task(
        prompt=full_prompt,
        session_id=session_id,
        continue_session=continue_session,
        model=model,
        agent=agent_name,
        timeout=args.get("timeout", 300),
    )

    # Mettre à jour la tâche avec les fichiers modifiés si succès
    if result.success:
        modified = await _get_modified_files(ctx)
        result.files_modified = modified

    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "session_id": result.session_id,
        "duration_ms": result.duration_ms,
        "files_modified": result.files_modified,
        "exit_code": result.exit_code,
    }


async def get_opencode_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Récupère le statut d'une session OpenCode."""
    session_id = args.get("session_id") or ctx.task.opencode_session_id
    if not session_id:
        return {"error": "Aucun session_id disponible"}

    client = get_opencode_client(ctx.settings)
    return await client.get_status(session_id)


async def get_opencode_output(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Récupère la sortie complète d'une session OpenCode (export)."""
    return await get_opencode_status(ctx, args)


async def run_tests(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Lance les tests (pytest) sur le repository ou ciblés."""
    work_dir = Path(ctx.work_dir)
    target = args.get("target")
    timeout = args.get("timeout", 120)

    cmd = ["python", "-m", "pytest", "-q"]
    if target:
        cmd.append(target)
    else:
        # Par défaut, tests ciblés sur les fichiers modifiés
        modified = await _get_modified_files(ctx)
        if modified:
            test_targets = _infer_test_targets(modified)
            if test_targets:
                cmd.extend(test_targets)

    env = os.environ.copy()
    env["OPENCODE_WORK_DIR"] = str(work_dir)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        output = stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")

        # Parser le résultat pytest
        passed = "passed" in output
        failed = "failed" in output
        return {
            "success": proc.returncode == 0,
            "output": output,
            "error": error if proc.returncode != 0 else None,
            "returncode": proc.returncode,
            "passed": passed,
            "failed": failed,
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": f"Timeout après {timeout}s"}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


async def analyze_failure(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Analyse un échec de test et propose une correction."""
    test_output = args.get("test_output")
    if not test_output:
        return {"error": "Sortie de test requise"}

    prompt = (
        "Analyse cet échec de test et propose une correction précise.\n\n"
        f"SORTIE TEST :\n{test_output}\n\n"
        "Réponds uniquement par un objet JSON :\n"
        '{"analysis": "cause racine", "fix": "correction proposée", "files": ["fichier1.py"]}'
    )

    client = get_opencode_client(ctx.settings)
    result = await client.run_task(prompt=prompt, timeout=60)
    if result.success:
        try:
            return json.loads(result.output)
        except json.JSONDecodeError:
            return {"analysis": "parsing échoué", "fix": result.output[:500], "files": []}
    return {"error": result.error or "Échec analyse"}


def _build_opencode_prompt(ctx: ToolContext, user_prompt: str) -> str:
    """Construit le prompt complet pour OpenCode avec le contexte."""
    task = ctx.task
    parts = [
        f"TÂCHE DE DÉVELOPPEMENT : {task.title}",
        f"DEMANDE : {task.request}",
        f"BRANCHE : {task.branch or 'master'}",
        f"REPOSITORY : {task.repository}",
        "",
        "INSTRUCTION :",
        user_prompt,
        "",
        "CONTEXTE SUPPLÉMENTAIRE :",
        json.dumps(ctx.payload, ensure_ascii=False, indent=2),
    ]
    return "\n".join(parts)


async def _get_modified_files(ctx: ToolContext) -> list[str]:
    """Récupère la liste des fichiers modifiés depuis le dernier commit."""
    work_dir = Path(ctx.work_dir)
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            files = [f for f in result.stdout.strip().splitlines() if f]
            # Ajouter aussi les staged
            result2 = subprocess.run(
                ["git", "diff", "--name-only", "--staged"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result2.returncode == 0:
                files.extend([f for f in result2.stdout.strip().splitlines() if f])
            return list(set(files))
    except Exception:
        pass
    return []


def _infer_test_targets(modified_files: list[str]) -> list[str]:
    """Déduit les cibles de test pertinentes depuis les fichiers modifiés."""
    targets = []
    for f in modified_files:
        if f.startswith("app/") and f.endswith(".py"):
            test_path = f.replace("app/", "tests/").replace(".py", "_test.py")
            if not test_path.startswith("tests/"):
                test_path = "tests/" + test_path
            targets.append(test_path)
    return list(set(targets))[:10]


DEVELOPMENT_SPECS = [
    ToolSpec(
        name="start_development_task",
        description="Initialise une tâche de développement : crée la branche dédiée.",
        input_schema={"type": "object", "properties": {}},
        handler=start_development_task,
        permission="development.execute",
        access="write",
    ),
    ToolSpec(
        name="ask_opencode",
        description="Envoie une instruction à OpenCode pour implémenter/analyser/corriger.",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Instruction pour OpenCode"},
                "session_id": {"type": "string", "description": "ID de session OpenCode (optionnel)"},
                "continue": {"type": "boolean", "description": "Continuer la session (défaut: true)"},
                "model": {"type": "string", "description": "Modèle à utiliser (optionnel)"},
                "agent": {"type": "string", "description": "Agent OpenCode (optionnel)"},
                "timeout": {"type": "integer", "description": "Timeout en secondes (défaut: 300)"},
            },
            "required": ["prompt"],
        },
        handler=ask_opencode,
        permission="development.execute",
        access="write",
    ),
    ToolSpec(
        name="get_opencode_status",
        description="Récupère le statut d'une session OpenCode.",
        input_schema={"type": "object", "properties": {"session_id": {"type": "string", "description": "ID de session (optionnel, défaut: tâche courante)"}}},
        handler=get_opencode_status,
        permission="development.read",
        access="read",
    ),
    ToolSpec(
        name="get_opencode_output",
        description="Récupère la sortie complète d'une session OpenCode.",
        input_schema={"type": "object", "properties": {"session_id": {"type": "string", "description": "ID de session (optionnel)"}}},
        handler=get_opencode_output,
        permission="development.read",
        access="read",
    ),
    ToolSpec(
        name="run_tests",
        description="Lance les tests (pytest) sur le repository ou ciblés.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Cible de test spécifique (optionnel)"},
                "timeout": {"type": "integer", "description": "Timeout en secondes (défaut: 120)"},
            },
        },
        handler=run_tests,
        permission="development.execute",
        access="write",
    ),
    ToolSpec(
        name="analyze_failure",
        description="Analyse un échec de test et propose une correction.",
        input_schema={
            "type": "object",
            "properties": {
                "test_output": {"type": "string", "description": "Sortie complète du test échoué"},
            },
            "required": ["test_output"],
        },
        handler=analyze_failure,
        permission="development.execute",
        access="write",
    ),
]