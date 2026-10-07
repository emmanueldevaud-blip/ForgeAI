import asyncio
import smtplib
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.ad_integration import ADGroupMapping
from app.models.module import Module, ModuleConfig
from app.models.rbac import Group, PermissionModel
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminPasswordReset,
    AiChatRequest,
    AiChatResponse,
    AiConversationDetail,
    AiConversationSummary,
    AiMessageItem,
    AiProviderSettings,
    AiProviderSettingsUpdate,
    AiSettingsResponse,
    AiSettingsUpdate,
    GroupCreate,
    GroupListParams,
    GroupListResponse,
    GroupResponse,
    GroupSummaryResponse,
    GroupUpdate,
    GroupUserAssign,
    GroupRoleAssign,
    GroupWithDetailsResponse,
    MessageResponse,
    PermissionCreate,
    PermissionListParams,
    PermissionListResponse,
    PermissionResponse,
    PermissionUpdate,
    RoleAssignRequest,
    RoleCreate,
    RoleListParams,
    RoleListResponse,
    RoleResponse,
    RoleUpdate,
    RoleWithPermissionsResponse,
    RolePermissionAssign,
    RolePermissionReplace,
    UserCreateAdmin,
    UserListParams,
    UserListResponse,
    UserToggleActive,
    UserUpdateAdmin,
    UserWithRolesResponse,
    SmtpSettingsResponse,
    SmtpSettingsUpdate,
    SmtpTestRequest,
)
from app.services.admin import AdminUserService
from app.services.audit import get_audit_service
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.ai_gateway.config_store import (
    AI_SETTINGS_FIELDS,
    SECRET_FIELDS,
    apply_from_db,
    db_key,
    effective_value,
    load_overrides,
)


router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"]
)

settings_router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


async def _get_administration_configs(db: AsyncSession) -> dict[str, ModuleConfig]:
    result = await db.execute(
        select(ModuleConfig)
        .join(Module)
        .where(Module.code == "administration")
    )
    return {config.key: config for config in result.scalars().all()}


@settings_router.get("/smtp", response_model=SmtpSettingsResponse)
async def get_smtp_settings(
    current_user: User = Depends(require_permission("settings_view")),
    db: AsyncSession = Depends(get_db),
):
    configs = await _get_administration_configs(db)
    get_value = lambda key, default="": configs.get(key).value if configs.get(key) and configs.get(key).value is not None else default
    return SmtpSettingsResponse(
        host=get_value("smtp_host"),
        port=int(get_value("smtp_port", "587")),
        username=get_value("smtp_username"),
        password_configured=bool(get_value("smtp_password")),
        use_tls=get_value("smtp_use_tls", "true").lower() == "true",
        use_ssl=get_value("smtp_use_ssl", "false").lower() == "true",
        from_email=get_value("smtp_from_email"),
        from_name=get_value("smtp_from_name", "ForgeAI"),
    )


@settings_router.put("/smtp", response_model=SmtpSettingsResponse)
async def update_smtp_settings(
    data: SmtpSettingsUpdate,
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    module_result = await db.execute(select(Module).where(Module.code == "administration"))
    module = module_result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=500, detail="Module Administration non trouvé")

    values = {
        "smtp_host": data.host,
        "smtp_port": str(data.port),
        "smtp_username": data.username,
        "smtp_use_tls": str(data.use_tls).lower(),
        "smtp_use_ssl": str(data.use_ssl).lower(),
        "smtp_from_email": data.from_email or "",
        "smtp_from_name": data.from_name,
    }
    if data.password is not None and data.password != "":
        values["smtp_password"] = data.password

    configs = await _get_administration_configs(db)
    for key, value in values.items():
        config = configs.get(key)
        if config:
            config.value = value
        else:
            db.add(ModuleConfig(
                module_id=module.id,
                key=key,
                value=value,
                value_type="boolean" if key in {"smtp_use_tls", "smtp_use_ssl"} else "string",
                is_secret=key == "smtp_password",
            ))
    await db.commit()
    return await get_smtp_settings(current_user=current_user, db=db)


@settings_router.post("/smtp/test", response_model=MessageResponse)
async def test_smtp_settings(
    data: SmtpTestRequest,
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    configs = await _get_administration_configs(db)
    get_value = lambda key, default="": configs.get(key).value if configs.get(key) and configs.get(key).value is not None else default
    smtp = {
        "host": get_value("smtp_host"),
        "port": int(get_value("smtp_port", "587")),
        "username": get_value("smtp_username"),
        "password": get_value("smtp_password"),
        "use_tls": get_value("smtp_use_tls", "true").lower() == "true",
        "use_ssl": get_value("smtp_use_ssl", "false").lower() == "true",
        "from_email": get_value("smtp_from_email"),
        "from_name": get_value("smtp_from_name", "ForgeAI"),
    }
    if not smtp["host"] or not smtp["from_email"]:
        raise HTTPException(status_code=400, detail="Enregistrez d'abord le serveur et l'adresse d'envoi SMTP")

    message = EmailMessage()
    message["From"] = f'{smtp["from_name"]} <{smtp["from_email"]}>'
    message["To"] = data.recipient
    message["Subject"] = "Test SMTP ForgeAI"
    message.set_content("Cet e-mail confirme que la configuration SMTP de ForgeAI fonctionne.")

    def send() -> None:
        smtp_class = smtplib.SMTP_SSL if smtp["use_ssl"] else smtplib.SMTP
        with smtp_class(smtp["host"], smtp["port"], timeout=30) as client:
            if smtp["use_tls"] and not smtp["use_ssl"]:
                client.starttls()
            if smtp["username"]:
                client.login(smtp["username"], smtp["password"])
            client.send_message(message)

    try:
        await asyncio.to_thread(send)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Échec du test SMTP : {exc}") from exc
    return {"message": f"E-mail de test envoyé à {data.recipient}"}


def _effective_ai_values(overrides: dict[str, str]) -> dict:
    """Valeurs effectives des paramètres IA : overlay DB > environnement."""
    from app.core.config import get_settings

    settings = get_settings()
    values = {field: getattr(settings, field) for field in AI_SETTINGS_FIELDS}
    by_key = {db_key(field): field for field in AI_SETTINGS_FIELDS}
    for key, raw in overrides.items():
        field = by_key.get(key)
        if field is not None:
            values[field] = effective_value(field, raw, values[field])
    return values


def _ai_provider_settings(values: dict, prefix: str) -> AiProviderSettings:
    return AiProviderSettings(
        enabled=values[f"{prefix}_ENABLED"],
        api_key_configured=bool(values[f"{prefix}_API_KEY"]),
        base_url=values[f"{prefix}_BASE_URL"],
        model=values[f"{prefix}_MODEL"],
    )


@settings_router.get("/ai", response_model=AiSettingsResponse)
async def get_ai_settings(
    current_user: User = Depends(require_permission("settings_view")),
    db: AsyncSession = Depends(get_db),
):
    values = _effective_ai_values(await load_overrides(db))
    return AiSettingsResponse(
        enabled=values["AI_GATEWAY_ENABLED"],
        default_provider=values["AI_DEFAULT_PROVIDER"],
        default_model=values["AI_DEFAULT_MODEL"],
        provider_order=values["AI_PROVIDER_ORDER"],
        ai_router_enabled=values.get("AI_ROUTER_ENABLED", True),
        ai_router_prefer_free=values.get("AI_ROUTER_PREFER_FREE", True),
        ai_router_cooldown_seconds=float(values.get("AI_ROUTER_COOLDOWN_SECONDS", 300.0)),
        timeout_seconds=values["AI_TIMEOUT_SECONDS"],
        max_retries=values["AI_MAX_RETRIES"],
        retry_backoff_seconds=values["AI_RETRY_BACKOFF_SECONDS"],
        web_search_enabled=values.get("WEB_SEARCH_ENABLED", True),
        web_search_provider=values.get("WEB_SEARCH_PROVIDER", "brave"),
        web_search_max_results=int(values.get("WEB_SEARCH_MAX_RESULTS", 8)),
        web_search_timeout_seconds=float(values.get("WEB_SEARCH_TIMEOUT_SECONDS", 15.0)),
        web_search_fallback_enabled=values.get("WEB_SEARCH_FALLBACK_ENABLED", True),
        web_search_cache_enabled=values.get("WEB_SEARCH_CACHE_ENABLED", True),
        web_search_cache_ttl_seconds=int(values.get("WEB_SEARCH_CACHE_TTL_SECONDS", 3600)),
        web_search_api_key_configured=bool(values.get("WEB_SEARCH_API_KEY")),
        groq=_ai_provider_settings(values, "GROQ"),
        gemini=_ai_provider_settings(values, "GEMINI"),
        openrouter=_ai_provider_settings(values, "OPENROUTER"),
    )


@settings_router.put("/ai", response_model=AiSettingsResponse)
async def update_ai_settings(
    data: AiSettingsUpdate,
    current_user: User = Depends(require_permission("settings_update")),
    db: AsyncSession = Depends(get_db),
):
    module_result = await db.execute(select(Module).where(Module.code == "administration"))
    module = module_result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=500, detail="Module Administration non trouvé")

    values: dict[str, str] = {
        "ai_gateway_enabled": str(data.enabled).lower(),
        "ai_default_provider": data.default_provider,
        "ai_default_model": data.default_model,
        "ai_provider_order": data.provider_order,
        "ai_router_enabled": str(data.ai_router_enabled).lower(),
        "ai_router_prefer_free": str(data.ai_router_prefer_free).lower(),
        "ai_router_cooldown_seconds": str(data.ai_router_cooldown_seconds),
        "ai_timeout_seconds": str(data.timeout_seconds),
        "ai_max_retries": str(data.max_retries),
        "ai_retry_backoff_seconds": str(data.retry_backoff_seconds),
        "web_search_enabled": str(data.web_search_enabled).lower(),
        "web_search_provider": data.web_search_provider,
        "web_search_max_results": str(data.web_search_max_results),
        "web_search_timeout_seconds": str(data.web_search_timeout_seconds),
        "web_search_fallback_enabled": str(data.web_search_fallback_enabled).lower(),
        "web_search_cache_enabled": str(data.web_search_cache_enabled).lower(),
        "web_search_cache_ttl_seconds": str(data.web_search_cache_ttl_seconds),
    }
    providers: dict[str, AiProviderSettingsUpdate] = {
        "groq": data.groq,
        "gemini": data.gemini,
        "openrouter": data.openrouter,
    }
    for prefix, provider in providers.items():
        values[f"{prefix}_enabled"] = str(provider.enabled).lower()
        values[f"{prefix}_base_url"] = provider.base_url
        values[f"{prefix}_model"] = provider.model
        if provider.api_key:
            values[f"{prefix}_api_key"] = provider.api_key

    if data.web_search_api_key is not None:
        values["web_search_api_key"] = data.web_search_api_key

    configs = await _get_administration_configs(db)
    for key, value in values.items():
        config = configs.get(key)
        if config:
            config.value = value
        else:
            db.add(ModuleConfig(
                module_id=module.id,
                key=key,
                value=value,
                value_type="boolean" if key.endswith("_enabled") else "string",
                is_secret=key in {db_key(field) for field in SECRET_FIELDS},
            ))
    await db.commit()
    await apply_from_db(db)
    return await get_ai_settings(current_user=current_user, db=db)


# ============================================================
# AI CHAT (Assistant IA via la passerelle centralisée)
# ============================================================

AI_CHAT_MODULE = "assistant"
AI_CHAT_HISTORY_LIMIT = 20
AI_CHAT_MAX_TOKENS = 2000
AI_CHAT_SYSTEM_PROMPT = (
    "Tu es l'assistant IA de ForgeAI, une application de gestion de données "
    "techniques de construction (chiffrage, métrés, maintenance, planning, "
    "administratif). Réponds en français, de façon claire et concise."
)


@settings_router.post("/ai/chat", response_model=AiChatResponse)
async def settings_ai_chat(
    data: AiChatRequest,
    current_user: User = Depends(require_permission("settings_view")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.maintenance import AIConversation, AIMessage

    if not data.message.strip():
        raise HTTPException(status_code=422, detail="Message vide")

    if data.conversation_id:
        result = await db.execute(
            select(AIConversation).where(
                AIConversation.id == data.conversation_id,
                AIConversation.user_id == current_user.id,
                AIConversation.module == AI_CHAT_MODULE,
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
            module=AI_CHAT_MODULE,
            title=data.message[:100],
        )
        db.add(conversation)
        await db.flush()
        prior_messages = []

    history = [{"role": m.role, "content": m.content} for m in prior_messages]
    history.append({"role": "user", "content": data.message})

    try:
        ai_response = await ai_gateway.generate(
            history=history,
            system_prompt=AI_CHAT_SYSTEM_PROMPT,
            task_type=data.task_type,
            max_tokens=AI_CHAT_MAX_TOKENS,
        )
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
        content=ai_response.text,
        model=ai_response.model_used,
        tokens_used=ai_response.tokens_output,
    ))
    await db.commit()

    return AiChatResponse(
        response=ai_response.text,
        conversation_id=conversation.id,
        provider=ai_response.provider_used,
        model=ai_response.model_used,
        latency=ai_response.latency,
        tokens_input=ai_response.tokens_input,
        tokens_output=ai_response.tokens_output,
    )


@settings_router.get("/ai/conversations", response_model=list[AiConversationSummary])
async def list_settings_ai_conversations(
    current_user: User = Depends(require_permission("settings_view")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.maintenance import AIConversation

    result = await db.execute(
        select(AIConversation)
        .where(
            AIConversation.user_id == current_user.id,
            AIConversation.module == AI_CHAT_MODULE,
        )
        .order_by(AIConversation.created_at.desc())
        .limit(50)
    )
    return [
        AiConversationSummary(
            id=c.id,
            title=c.title,
            module=c.module,
            created_at=c.created_at,
        )
        for c in result.scalars().all()
    ]


@settings_router.get("/ai/conversations/{conversation_id}", response_model=AiConversationDetail)
async def get_settings_ai_conversation(
    conversation_id: int,
    current_user: User = Depends(require_permission("settings_view")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.maintenance import AIConversation, AIMessage

    result = await db.execute(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user.id,
            AIConversation.module == AI_CHAT_MODULE,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation non trouvée")

    result = await db.execute(
        select(AIMessage)
        .where(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.created_at)
    )
    return AiConversationDetail(
        id=conversation.id,
        title=conversation.title,
        module=conversation.module,
        messages=[
            AiMessageItem(role=m.role, content=m.content, created_at=m.created_at)
            for m in result.scalars().all()
        ],
    )


@settings_router.get("/ai/stats")
async def get_settings_ai_stats(
    current_user: User = Depends(require_permission("settings_view")),
):
    return ai_gateway.get_stats()


async def get_admin_service(
    current_user: User = Depends(
        require_permission("admin.access")
    ),
    db: AsyncSession = Depends(get_db),
) -> AdminUserService:

    audit = await get_audit_service(db)

    return AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )


# ============================================================
# GROUPS
# ============================================================

@router.get(
    "/groups",
    response_model=GroupListResponse
)
async def list_groups(
    params: GroupListParams = Depends(),
    current_user: User = Depends(
        require_permission("group_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    groups, total = await service.search_groups(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        is_active=params.is_active,
        source=params.source,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    group_list = []

    for g in groups:
        result = await db.execute(
            select(Group)
            .options(
                selectinload(Group.users),
                selectinload(Group.roles)
            )
            .where(Group.id == g.id)
        )

        group_with_details = result.scalar_one()

        group_list.append(
            GroupResponse(
                id=g.id,
                code=g.code,
                name=g.name,
                description=g.description,
                is_active=g.is_active,
                source=g.source,
                ad_dn=g.ad_dn,
                created_at=g.created_at,
                updated_at=g.updated_at,
                user_count=len(group_with_details.users),
                role_count=len(group_with_details.roles),
            )
        )

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return GroupListResponse(
        groups=group_list,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_group(
    group_data: GroupCreate,
    current_user: User = Depends(
        require_permission("group_create")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group_dict = group_data.model_dump()

    group = await service.create_group(
        group_dict
    )

    return GroupResponse.model_validate(
        group,
        from_attributes=True
    )


@router.get(
    "/groups/{group_id}",
    response_model=GroupWithDetailsResponse
)
async def get_group(
    group_id: int,
    current_user: User = Depends(
        require_permission("group_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    return GroupWithDetailsResponse.model_validate(
        group,
        from_attributes=True
    )


@router.patch(
    "/groups/{group_id}",
    response_model=GroupResponse
)
async def update_group(
    group_id: int,
    updates: GroupUpdate,
    current_user: User = Depends(
        require_permission("group_update")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    if group.source == "ad":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Les informations d'un groupe AD ne peuvent pas être modifiées depuis ForgeAI",
        )

    group = await service.update_group(
        group,
        update_data
    )

    return GroupResponse.model_validate(
        group,
        from_attributes=True
    )


@router.delete(
    "/groups/{group_id}",
    response_model=MessageResponse
)
async def delete_group(
    group_id: int,
    current_user: User = Depends(
        require_permission("group_delete")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    if group.source == "ad":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un groupe AD ne peut pas être supprimé depuis ForgeAI",
        )

    await service.delete_group(group)

    return MessageResponse(
        message="Groupe supprimé"
    )


@router.post(
    "/groups/{group_id}/users",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_user_to_group(
    group_id: int,
    user_assign: GroupUserAssign,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    try:
        await service.add_user_to_group(
            group_id,
            user_assign.user_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return MessageResponse(
        message="Utilisateur ajouté au groupe"
    )


@router.delete(
    "/groups/{group_id}/users/{user_id}",
    response_model=MessageResponse
)
async def remove_user_from_group(
    group_id: int,
    user_id: int,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    removed = await service.remove_user_from_group(
        group_id,
        user_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cet utilisateur n'est pas membre du groupe",
        )

    return MessageResponse(
        message="Utilisateur retiré du groupe"
    )


@router.post(
    "/groups/{group_id}/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_role_to_group(
    group_id: int,
    role_assign: GroupRoleAssign,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    group = await service.get_group_with_details(
        group_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé",
        )

    role = await service.get_role_by_id(
        role_assign.role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if not role.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce rôle n'est pas actif",
        )

    try:
        await service.add_role_to_group(
            group_id,
            role_assign.role_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.delete(
    "/groups/{group_id}/roles/{role_id}",
    response_model=MessageResponse
)
async def remove_role_from_group(
    group_id: int,
    role_id: int,
    current_user: User = Depends(
        require_permission("group_manage_members")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    removed = await service.remove_role_from_group(
        group_id,
        role_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ce rôle n'est pas assigné à ce groupe",
        )

    return MessageResponse(
        message="Rôle retiré du groupe"
    )


# ============================================================
# ROLES
# ============================================================

@router.get(
    "/roles",
    response_model=RoleListResponse
)
async def list_roles(
    params: RoleListParams = Depends(),
    current_user: User = Depends(
        require_permission("role_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    roles, total = await service.search_roles(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        is_active=params.is_active,
        is_system=params.is_system,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    role_responses = [
        RoleResponse.model_validate(
            role,
            from_attributes=True
        )
        for role in roles
    ]

    # La colonne « Groupes » reflète aussi les mappings AD actifs de
    # l'onglet Active Directory, y compris lorsqu'un groupe AD n'existe
    # pas (encore) en base : sans cela, un mapping vers un groupe
    # absent resterait invisible côté Rôles.
    active_mappings = (
        await db.execute(
            select(ADGroupMapping).where(
                ADGroupMapping.is_active.is_(True)
            )
        )
    ).scalars().all()

    mapped_names: dict[str, list[str]] = {}
    for mapping in active_mappings:
        mapped_names.setdefault(mapping.role_code, []).append(
            mapping.ad_group_cn
        )

    for role_response in role_responses:
        shown = {group.name for group in role_response.groups}
        for group_name in mapped_names.get(role_response.code, []):
            if group_name in shown:
                continue
            role_response.groups.append(
                GroupSummaryResponse(
                    id=None,
                    code=group_name,
                    name=group_name,
                    source="ad",
                    is_active=True,
                )
            )
            shown.add(group_name)

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return RoleListResponse(
        roles=role_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_role(
    role_data: RoleCreate,
    current_user: User = Depends(
        require_permission("role_create")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role_dict = role_data.model_dump()

    role = await service.create_role(
        role_dict
    )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.get(
    "/roles/{role_id}",
    response_model=RoleWithPermissionsResponse
)
async def get_role(
    role_id: int,
    current_user: User = Depends(
        require_permission("role_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_with_permissions(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    return RoleWithPermissionsResponse.model_validate(
        role,
        from_attributes=True
    )


@router.patch(
    "/roles/{role_id}",
    response_model=RoleResponse
)
async def update_role(
    role_id: int,
    updates: RoleUpdate,
    current_user: User = Depends(
        require_permission("role_update")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de modifier un rôle système",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    role = await service.update_role(
        role,
        update_data
    )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.delete(
    "/roles/{role_id}",
    response_model=MessageResponse
)
async def delete_role(
    role_id: int,
    current_user: User = Depends(
        require_permission("role_delete")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer un rôle système",
        )

    await service.delete_role(role)

    return MessageResponse(
        message="Rôle supprimé"
    )


@router.post(
    "/roles/{role_id}/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_permission_to_role(
    role_id: int,
    perm_assign: RolePermissionAssign,
    current_user: User = Depends(
        require_permission("role_manage_permissions")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    permission = await service.get_permission_by_id(
        perm_assign.permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    try:
        await service.add_permission_to_role(
            role_id,
            perm_assign.permission_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    response_model=MessageResponse
)
async def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    current_user: User = Depends(
        require_permission("role_manage_permissions")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    removed = await service.remove_permission_from_role(
        role_id,
        permission_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cette permission n'est pas assignée à ce rôle",
        )

    return MessageResponse(
        message="Permission retirée du rôle"
    )


@router.put(
    "/roles/{role_id}/permissions",
    response_model=RoleWithPermissionsResponse
)
async def replace_role_permissions(
    role_id: int,
    body: RolePermissionReplace,
    current_user: User = Depends(
        require_permission("role_manage_permissions")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    try:
        role = await service.replace_role_permissions(
            role_id,
            body.permission_ids
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return RoleWithPermissionsResponse.model_validate(
        role,
        from_attributes=True
    )


@router.get(
    "/roles/{role_id}/permissions",
    response_model=list[PermissionResponse]
)
async def list_role_permissions(
    role_id: int,
    current_user: User = Depends(
        require_permission("role_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    role = await service.get_role_with_permissions(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    return [
        PermissionResponse.model_validate(
            permission,
            from_attributes=True
        )
        for permission in role.permissions
    ]


# ============================================================
# PERMISSIONS
# ============================================================

@router.get(
    "/permissions",
    response_model=PermissionListResponse
)
async def list_permissions(
    params: PermissionListParams = Depends(),
    current_user: User = Depends(
        require_permission("permission_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permissions, total = await service.search_permissions(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        module=params.module,
        is_system=params.is_system,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    permission_responses = [
        PermissionResponse.model_validate(
            permission,
            from_attributes=True
        )
        for permission in permissions
    ]

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return PermissionListResponse(
        permissions=permission_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_permission(
    permission_data: PermissionCreate,
    current_user: User = Depends(
        require_permission("permission_create")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission_dict = permission_data.model_dump()

    permission = await service.create_permission(
        permission_dict
    )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.get(
    "/permissions/{permission_id}",
    response_model=PermissionResponse
)
async def get_permission(
    permission_id: int,
    current_user: User = Depends(
        require_permission("permission_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission = await service.get_permission_by_id(
        permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.patch(
    "/permissions/{permission_id}",
    response_model=PermissionResponse
)
async def update_permission(
    permission_id: int,
    updates: PermissionUpdate,
    current_user: User = Depends(
        require_permission("permission_update")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission = await service.get_permission_by_id(
        permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    if permission.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de modifier une permission système",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    permission = await service.update_permission(
        permission,
        update_data
    )

    return PermissionResponse.model_validate(
        permission,
        from_attributes=True
    )


@router.delete(
    "/permissions/{permission_id}",
    response_model=MessageResponse
)
async def delete_permission(
    permission_id: int,
    current_user: User = Depends(
        require_permission("permission_delete")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    permission = await service.get_permission_by_id(
        permission_id
    )

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée",
        )

    if permission.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer une permission système",
        )

    await service.delete_permission(
        permission
    )

    return MessageResponse(
        message="Permission supprimée"
    )


# ============================================================
# USERS
# ============================================================

@router.get(
    "",
    response_model=UserListResponse
)
async def list_users(
    params: UserListParams = Depends(),
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    users, total = await service.search_users(
        page=params.page,
        page_size=params.page_size,
        search=params.search,
        role=params.role,
        is_active=params.is_active,
        source=params.source,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )

    user_responses = [
        UserWithRolesResponse.model_validate(
            user,
            from_attributes=True
        )
        for user in users
    ]

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return UserListResponse(
        users=user_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{user_id}/permissions",
    response_model=list[PermissionResponse]
)
async def get_user_permissions(
    user_id: int,
    current_user: User = Depends(
        require_permission("admin.access")
    ),
    db: AsyncSession = Depends(get_db),
):
    from app.services.rbac import RBACService

    rbac = RBACService(db)

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
    )

    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    permissions = await rbac.get_user_permissions(
        user
    )

    # Legacy admin users do not receive RBAC access implicitly. Keep the
    # permissions screen informative without changing effective authorization.
    if not permissions and user.role == UserRole.ADMIN:
        permissions = {"*"}

    if "*" in permissions:
        result = await db.execute(
            select(PermissionModel)
        )

        permissions_list = result.scalars().all()

        permission_responses = [
            PermissionResponse.model_validate(
                permission,
                from_attributes=True
            )
            for permission in permissions_list
        ]

        permission_responses.append(
            PermissionResponse(
                id=0,
                code="*",
                name="Accès total (admin)",
                description=(
                    "Permission wildcard pour administrateurs"
                ),
                module="rbac",
                is_system=True
            )
        )

        return permission_responses

    result = await db.execute(
        select(PermissionModel)
        .where(
            PermissionModel.code.in_(permissions)
        )
    )

    permissions_list = result.scalars().all()

    return [
        PermissionResponse.model_validate(
            permission,
            from_attributes=True
        )
        for permission in permissions_list
    ]


@router.get(
    "/{user_id}",
    response_model=UserWithRolesResponse
)
async def get_user(
    user_id: int,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.post(
    "",
    response_model=UserWithRolesResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_user(
    user_data: UserCreateAdmin,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    from app.core.config import get_settings

    settings = get_settings()

    if (
        not settings.AUTH_LOCAL_ENABLED
        and user_data.source == "local"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Création d'utilisateurs locaux désactivée",
        )

    from sqlalchemy import text

    existing = await service.db.execute(
        text(
            "SELECT 1 FROM users "
            "WHERE username = :username "
            "OR email = :email"
        ),
        {
            "username": user_data.username,
            "email": user_data.email
        },
    )

    if existing.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom d'utilisateur ou email déjà utilisé",
        )

    user_dict = user_data.model_dump()

    user = await service.create_user(
        user_dict
    )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.patch(
    "/{user_id}",
    response_model=UserWithRolesResponse
)
async def update_user(
    user_id: int,
    updates: UserUpdateAdmin,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    update_data = updates.model_dump(
        exclude_unset=True
    )

    if user.source == "ad":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Les informations d'un utilisateur AD ne peuvent pas être modifiées depuis ForgeAI.",
        )

    group_ids = update_data.pop("group_ids", None)

    user = await service.update_user(
        user,
        update_data
    )

    if group_ids is not None:
        user = await service.set_user_groups(
            user_id,
            group_ids
        )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.post(
    "/{user_id}/toggle-active",
    response_model=UserWithRolesResponse
)
async def toggle_user_active(
    user_id: int,
    toggle: UserToggleActive,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if (
        user.id == service.current_user.id
        and not toggle.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de désactiver son propre compte",
        )

    if user.source == "ad":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le statut d'un utilisateur AD est géré par l'Active Directory",
        )

    user = await service.toggle_active(
        user,
        toggle.is_active
    )

    return UserWithRolesResponse.model_validate(
        user,
        from_attributes=True
    )


@router.post(
    "/{user_id}/reset-password",
    response_model=MessageResponse
)
async def reset_password(
    user_id: int,
    reset_data: AdminPasswordReset,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if user.source != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de réinitialiser le mot de passe pour un compte AD",
        )

    await service.reset_password(
        user,
        reset_data.new_password
    )

    return MessageResponse(
        message="Mot de passe réinitialisé"
    )


@router.delete(
    "/{user_id}",
    response_model=MessageResponse
)
async def delete_user(
    user_id: int,
    service: AdminUserService = Depends(
        get_admin_service
    ),
):
    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    if user.id == service.current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer son propre compte",
        )

    if user.source == "ad":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Impossible de supprimer un utilisateur provenant de l'Active Directory",
        )

    await service.delete_user(user)

    return MessageResponse(
        message="Utilisateur supprimé"
    )


@router.post(
    "/{user_id}/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED
)
async def assign_role_to_user(
    user_id: int,
    role_assign: RoleAssignRequest,
    current_user: User = Depends(
        require_permission("user_manage_roles")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    role = await service.get_role_by_id(
        role_assign.role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    if not role.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce rôle n'est pas actif",
        )

    try:
        await service.assign_role(
            user_id,
            role_assign.role_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return RoleResponse.model_validate(
        role,
        from_attributes=True
    )


@router.delete(
    "/{user_id}/roles/{role_id}",
    response_model=MessageResponse
)
async def remove_role_from_user(
    user_id: int,
    role_id: int,
    current_user: User = Depends(
        require_permission("user_manage_roles")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    service = AdminUserService(
        db,
        audit=audit,
        current_user=current_user
    )

    user = await service.get_user_with_roles(
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé",
        )

    role = await service.get_role_by_id(
        role_id
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé",
        )

    removed = await service.remove_role(
        user_id,
        role_id
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ce rôle n'est pas assigné à l'utilisateur",
        )

    return MessageResponse(
        message="Rôle retiré de l'utilisateur"
    )
