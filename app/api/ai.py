"""Router de l'assistant IA (module ai_assistant).

Extrait du router maintenance : ces endpoints forment le vrai router IA,
protege par le statut du module `ai_assistant` en plus des permissions.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_module_enabled, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.maintenance import (
    AIChatRequest,
    AIChatResponse,
    AIOptionsResponse,
)
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.rbac import RBACService
from app.services.sport import SportService
from app.services.sport_agent import agent_enabled, run_agent_trigger
from app.services.sport_ai import get_sport_ai_provider

logger = logging.getLogger(__name__)

MODULE_PERMISSION_MAP = {
    "maintenance": "maintenance.view",
    "agenda": "agenda.access",
    "sport": "sport.access",
    "buildings": "building.view",
    "housing": "housing.view",
    "equipment": "equipment.view",
    "volunteers": "volunteers.view",
    "development": "development.execute",
}


router = APIRouter(
    prefix="/ai",
    tags=["ai"],
    dependencies=[Depends(require_module_enabled("ai_assistant"))],
)


# ============================================================
# AI CHAT
# ============================================================

AI_CHAT_HISTORY_LIMIT = 20
AI_CHAT_MAX_TOKENS = 2000
AI_CHAT_SYSTEM_PROMPT = (
    "Tu es l'assistant IA de ForgeAI, une application de gestion de données "
    "techniques de construction. Tu peux aider sur tous les modules de "
    "l'ERP (chiffrage, métrés, maintenance, planning, administratif, logement, "
    "équipement, sport, agenda, volontaires, etc.). Réponds en français, de "
    "façon claire et concise."
)

# Lorsque la question évoque le sport, l'assistant répond via le coach IA du
# module Sport, qui dispose réellement des données de l'athlète.
_SPORT_QUESTION_RE = re.compile(
    r"sport|activit|entraînement|entrainement|séance|seance|sorti|footing|running|"
    r"course|vélo|velo|cardio|fréquence|frequence|musculation|natation|"
    r"coach|objectif|dénivelé|denivele|forme|progress|évolu|evolu|historique|"
    r"semaine|mois|charge|\bkm\b",
    re.IGNORECASE,
)

# Détection des demandes de développement : mots-clés techniques
_DEVELOPMENT_QUESTION_RE = re.compile(
    r"(ajoute|ajouter|crée|créer|modifie|modifier|corrige|corriger|implémente|implémenter|"
    r"développe|développer|refactor|refactorise|refactoriser|optimise|optimiser|"
    r"bug|erreur|problème|fix|patch|feature|fonctionnalité|module|api|endpoint|"
    r"base de données|database|migration|schéma|model|repository|git|commit|push|"
    r"déploie|déployer|deploy|test|tests|pytest|lint|docker|container|service|"
    r"forgeai|application|code|fichier|classe|fonction|méthode|variable|import)",
    re.IGNORECASE,
)


async def _build_sport_context(db: AsyncSession, user: User, question: str | None = None) -> dict | None:
    """Contexte du coach sport pour l'utilisateur, ou None si indisponible."""
    try:
        service = SportService(db, user)
        athlete = await service.get_or_create_athlete()
        return await service.build_coach_context(athlete, question=question)
    except Exception:
        logger.warning("[AI-CHAT] Contexte sport indisponible", exc_info=True)
        return None


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    data: AIChatRequest,
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.maintenance import AIConversation, AIMessage

    if not data.message.strip():
        raise HTTPException(status_code=422, detail="Message vide")

    module_perm = MODULE_PERMISSION_MAP.get(data.module)
    if module_perm and not await RBACService(db).user_has_permission(current_user, module_perm):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{module_perm}' requise pour le module {data.module}",
        )

    # Module de la conversation : déduit si le client n'en envoie pas
    # (l'assistant IA global n'est plus branché sur un module unique).
    sport_allowed = bool(_SPORT_QUESTION_RE.search(data.message))
    if sport_allowed:
        sport_allowed = await RBACService(db).user_has_permission(current_user, "sport.access")

    # Détection des demandes de développement : mode explicite ou mots-clés
    development_explicit = data.module == "development"
    development_allowed = development_explicit or bool(_DEVELOPMENT_QUESTION_RE.search(data.message))
    if development_allowed:
        development_allowed = await RBACService(db).user_has_permission(current_user, "development.execute")

    conversation_module = data.module or (
        "development" if development_allowed else ("sport" if sport_allowed else "maintenance")
    )

    # Sélection explicite de l'agent via le sélecteur : elle prime sur la
    # détection par mots-clés. "Automatique" conserve le comportement par défaut.
    requested_agent = (data.agent or "").strip()
    force_sport_agent = requested_agent == "Coach sportif"
    force_general_agent = requested_agent == "Assistant général"
    force_development_agent = requested_agent == "Agent Développement"

    if force_sport_agent:
        development_explicit = False
        development_allowed = False
        sport_allowed = await RBACService(db).user_has_permission(current_user, "sport.access")
    elif force_general_agent:
        sport_allowed = False
        development_explicit = False
        development_allowed = False
    elif force_development_agent:
        sport_allowed = False
        development_explicit = False
        development_allowed = await RBACService(db).user_has_permission(current_user, "development.execute")

    if data.conversation_id:
        result = await db.execute(
            select(AIConversation).where(
                AIConversation.id == data.conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation non trouvée")
        result = await db.execute(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation.id)
            .order_by(AIMessage.created_at.asc(), AIMessage.id.asc())
        )
        all_messages = result.scalars().all()
        prior_messages = all_messages[-AI_CHAT_HISTORY_LIMIT:]
    else:
        conversation = AIConversation(
            user_id=current_user.id,
            module=conversation_module,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            title=data.message[:100],
        )
        db.add(conversation)
        await db.flush()
        prior_messages = []

    history = [{"role": m.role, "content": m.content} for m in prior_messages]
    # Histoire sans le message courant : l'Agent Sport reçoit sa mission
    # (qui contient la question) comme dernier message utilisateur.
    agent_history = list(history)
    history.append({"role": "user", "content": data.message})

    ai_text: str | None = None
    ai_model: str | None = None
    ai_tokens: int | None = None

    if sport_allowed and agent_enabled():
        try:
            outcome = await run_agent_trigger(
                db,
                current_user,
                "user_request",
                payload={"question": data.message},
                history=agent_history,
            )
        except Exception:
            logger.exception("[AI-CHAT] Échec Agent Sport (user %s)", current_user.id)
            outcome = {}
        if outcome.get("status") == "completed":
            answer = (outcome.get("answer") or outcome.get("summary") or "").strip()
            ai_text = answer or "Demande prise en charge par le coach sportif."
            ai_model = outcome.get("model") or outcome.get("provider") or "sport-agent"
            actual_agent = "Coach sportif"
            actual_provider = outcome.get("provider") or "sport-agent"
            actual_model = outcome.get("model") or outcome.get("provider") or "sport-agent"
            logger.info(
                "[AI-CHAT] event=agent_answer execution=%s actions=%s",
                outcome.get("execution_id"),
                outcome.get("actions"),
            )

    # Agent Développement : uniquement en mode explicite (module="development")
    if ai_text is None and development_allowed and (development_explicit or force_development_agent):
        try:
            from app.services.development_agent.service import run_development_trigger
            from app.core.config import get_settings
            outcome = await run_development_trigger(
                db,
                current_user,
                "user_request",
                payload={"question": data.message, "history": agent_history},
                request=data.message,
            )
        except Exception:
            logger.exception("[AI-CHAT] Échec Agent Développement (user %s)", current_user.id)
            outcome = {}
        if outcome.get("status") in ("ready_for_review", "completed", "analyzing", "planning", "developing", "testing", "fixing"):
            status_map = {
                "analyzing": "Analyse du repository en cours...",
                "planning": "Planification du développement...",
                "developing": "Développement en cours via OpenCode...",
                "testing": "Exécution des tests...",
                "fixing": "Correction des erreurs...",
                "ready_for_review": "Développement terminé, en attente de validation.",
                "completed": "Tâche terminée.",
            }
            answer = outcome.get("answer") or status_map.get(outcome.get("status"), "Demande prise en charge par l'Agent Développement.")
            if outcome.get("task_id"):
                answer += f"\n\nTâche : {outcome['task_id']}"
                if outcome.get("branch"):
                    answer += f" (branche : {outcome['branch']})"
            ai_text = answer
            ai_model = "development-agent"
            actual_agent = "Agent Développement"
            actual_provider = "development-agent"
            actual_model = "development-agent"
            logger.info(
                "[AI-CHAT] event=development_agent_answer task=%s status=%s",
                outcome.get("task_id"),
                outcome.get("status"),
            )
        else:
            ai_text = outcome.get("error") or "Agent Développement indisponible."
            ai_model = "development-agent"
            actual_agent = "Agent Développement"
            actual_provider = "development-agent"
            actual_model = "development-agent"
            logger.warning(
                "[AI-CHAT] event=development_agent_unavailable status=%s",
                outcome.get("status"),
            )

    sport_context = None
    if ai_text is None and sport_allowed:
        sport_context = await _build_sport_context(db, current_user, data.message)

    if ai_text is None:
        try:
            if sport_context is not None:
                sport_result = await get_sport_ai_provider().answer(data.message, sport_context)
                ai_text = sport_result.get("answer")
                ai_model = sport_result.get("provider")
                ai_tokens = None
                actual_agent = "Coach sportif"
                actual_provider = sport_result.get("provider")
                actual_model = sport_result.get("model")
                fallback_info = None
            else:
                # Utiliser la sélection de l'utilisateur si fournie
                preferred_provider = data.llm_provider if data.llm_provider and data.llm_provider != "auto" else None
                model = data.llm_model if data.llm_model and data.llm_model != "auto" else "auto"

                ai_response = await ai_gateway.generate(
                    history=history,
                    system_prompt=AI_CHAT_SYSTEM_PROMPT,
                    max_tokens=AI_CHAT_MAX_TOKENS,
                    preferred_provider=preferred_provider,
                    model=model,
                )
                ai_text = ai_response.text
                ai_model = ai_response.model_used
                ai_tokens = ai_response.tokens_output
                actual_agent = "Assistant général"
                actual_provider = ai_response.provider_used
                actual_model = ai_response.model_used
                fallback_info = None
                if ai_response.fallback_used:
                    fallback_info = f"Fallback automatique utilisé (provider: {actual_provider}, modèle: {actual_model})"
        except AIGatewayError as exc:
            await db.rollback()
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.add(AIMessage(
        conversation_id=conversation.id,
        role="user",
        content=data.message,
    ))
    db.add(AIMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=ai_text,
        model=ai_model,
        tokens_used=ai_tokens,
    ))
    await db.commit()

    return AIChatResponse(
        response=ai_text,
        conversation_id=conversation.id,
        model=ai_model,
        actual_agent=actual_agent if 'actual_agent' in locals() else None,
        actual_provider=actual_provider if 'actual_provider' in locals() else None,
        actual_model=actual_model if 'actual_model' in locals() else None,
        requested_agent=data.agent,
        requested_provider=data.llm_provider,
        requested_model=data.llm_model,
        fallback_info=fallback_info if 'fallback_info' in locals() else None,
    )


@router.get("/conversations")
async def list_ai_conversations(
    module: Optional[str] = None,
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.maintenance import AIConversation

    query = select(AIConversation).where(AIConversation.user_id == current_user.id)
    if module:
        query = query.where(AIConversation.module == module)
    query = query.order_by(AIConversation.created_at.desc()).limit(50)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "module": c.module,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in conversations
        ]
    }


@router.get("/options", response_model=AIOptionsResponse)
async def get_ai_options(
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    """Retourne les agents et modèles LLM disponibles pour le sélecteur."""
    from app.services.ai_gateway import ai_gateway
    from app.services.ai_gateway.models import MODEL_CATALOG
    from app.core.config import get_settings

    settings = get_settings()

    # Agent Développement : actif seulement si le flag est activé ET que le
    # binaire OpenCode est détecté (sinon le mode développement est masqué).
    development_agent_enabled = False
    if settings.DEVELOPMENT_AGENT_ENABLED:
        try:
            from app.services.development_agent.opencode import get_opencode_client
            development_agent_enabled = get_opencode_client(settings).is_available()
        except Exception:
            development_agent_enabled = False

    # Agents disponibles
    agents = ["Automatique", "Assistant général"]
    rbac = RBACService(db)
    if await rbac.user_has_permission(current_user, "sport.access"):
        agents.append("Coach sportif")
    if development_agent_enabled and await rbac.user_has_permission(current_user, "development.execute"):
        agents.append("Agent Développement")

    # Modèles LLM depuis le catalogue et la configuration
    llm_providers = []

    # Modèles OpenCode (si disponibles)
    try:
        from app.services.ai.model_router import discover_opencode_models
        opencode_models = discover_opencode_models()
        for m in opencode_models:
            if m.get("free") is True:
                llm_providers.append({
                    "provider": "opencode",
                    "model": m["id"],
                    "display_name": f"OpenCode / {m['id']}",
                    "free": True,
                })
    except Exception:
        pass

    # Modèles AI Gateway (catalogue + config)
    for task_type, providers in MODEL_CATALOG.items():
        for provider_name, model in providers.items():
            display = f"{provider_name.capitalize()} / {model}"
            llm_providers.append({
                "provider": provider_name,
                "model": model,
                "display_name": display,
                "free": False,
            })

    # Dédupliquer
    seen = set()
    unique_providers = []
    for p in llm_providers:
        key = (p["provider"], p["model"])
        if key not in seen:
            seen.add(key)
            unique_providers.append(p)

    return AIOptionsResponse(
        agents=agents,
        llm_providers=unique_providers,
        development_agent_enabled=development_agent_enabled,
    )


@router.get("/conversations/{conversation_id}")
async def get_ai_conversation(
    conversation_id: int,
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.maintenance import AIConversation, AIMessage

    result = await db.execute(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation non trouvée")

    result = await db.execute(
        select(AIMessage).where(
            AIMessage.conversation_id == conversation_id
        ).order_by(AIMessage.created_at)
    )
    messages = result.scalars().all()

    return {
        "id": conversation.id,
        "title": conversation.title,
        "module": conversation.module,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_ai_conversation(
    conversation_id: int,
    current_user: User = Depends(require_permission("ai.use")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, delete
    from app.models.maintenance import AIConversation, AIMessage

    result = await db.execute(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation non trouvée")

    # Delete messages first (foreign key constraint)
    await db.execute(
        delete(AIMessage).where(AIMessage.conversation_id == conversation_id)
    )
    # Delete conversation
    await db.execute(
        delete(AIConversation).where(AIConversation.id == conversation_id)
    )
    await db.commit()

    return {"success": True, "message": "Conversation supprimée"}
