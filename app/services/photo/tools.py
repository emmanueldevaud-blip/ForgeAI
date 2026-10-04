"""Outils Photo pour l'Assistant IA ForgeAI.

Même patron que ``sport_agent``/``development_agent`` : un registre qui
vérifie la permission RBAC de chaque outil avant exécution. L'assistant
global peut consommer ``get_photo_tool_registry()`` sans duplication du
système de routage IA (voir docs/photos.md pour le branchement).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.services.rbac import RBACService

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: AsyncSession
    user: User
    settings: Any
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], Awaitable[Any]]
    permission: str = "photos.view"
    access: str = "read"
    requires_confirmation: bool = False


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "data": self.data}
        return {"ok": False, "error": self.error}


class PhotoToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Outil déjà enregistré : {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "access": spec.access,
            }
            for spec in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    async def call(
        self, ctx: ToolContext, name: str, arguments: dict[str, Any] | None = None
    ) -> ToolResult:
        args = arguments or {}
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(ok=False, error=f"outil_inconnu:{name}")

        if spec.permission:
            allowed = await RBACService(ctx.db).user_has_permission(
                ctx.user, spec.permission
            )
            if not allowed:
                logger.warning(
                    "[PHOTO-TOOL] tool_denied name=%s permission=%s user=%s",
                    name,
                    spec.permission,
                    ctx.user.id,
                )
                return ToolResult(ok=False, error=f"permission_denied:{spec.permission}")

        started = time.monotonic()
        try:
            data = await spec.handler(ctx, args)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[PHOTO-TOOL] tool_failed name=%s", name)
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {str(exc) or 'erreur'}")
        logger.info(
            "[PHOTO-TOOL] tool_call name=%s access=%s duration_ms=%d",
            name,
            spec.access,
            int((time.monotonic() - started) * 1000),
        )
        return ToolResult(ok=True, data=data)


async def _search_photos(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.schemas.photos import PhotoListParams
    from app.services.photo.service import PhotoService

    service = PhotoService(ctx.db, ctx.user)
    params = PhotoListParams(
        page=1,
        page_size=min(int(args.get("limit", 20) or 20), 100),
        search=args.get("query"),
        favorite=args.get("favorite"),
        tag=args.get("tag"),
        person_id=args.get("person_id"),
    )
    query = (args.get("query") or "").strip()
    if query and not (args.get("tag") or args.get("person_id")):
        items, total, _ = await service.search_natural(query, params)
    else:
        items, total, _ = await service.list_photos(params)
    return {
        "total": total,
        "photos": [
            {
                "id": photo.id,
                "title": photo.title,
                "filename": photo.original_filename,
                "taken_at": photo.taken_at.isoformat(),
                "is_favorite": photo.is_favorite,
            }
            for photo in items
        ],
    }


async def _get_photo(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.services.photo.service import PhotoNotFound, PhotoService

    service = PhotoService(ctx.db, ctx.user)
    try:
        detail = await service.get_photo_detail(int(args["photo_id"]))
    except PhotoNotFound:
        return {"error": "photo_introuvable"}
    photo = detail["photo"]
    return {
        "id": photo.id,
        "title": photo.title,
        "filename": photo.original_filename,
        "taken_at": photo.taken_at.isoformat(),
        "width": photo.width,
        "height": photo.height,
        "camera": photo.camera_model,
        "is_favorite": photo.is_favorite,
        # detail["tags"] contient des dicts (pas des modèles PhotoTag).
        "tags": [tag["name"] for tag in detail["tags"]],
        "place": photo.place.label if photo.place else None,
    }


async def _list_albums(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.schemas.photos import PhotoAlbumListParams
    from app.services.photo.service import PhotoService

    service = PhotoService(ctx.db, ctx.user)
    rows, total = await service.list_albums(
        PhotoAlbumListParams(page=1, page_size=min(int(args.get("limit", 50) or 50), 200))
    )
    return {
        "total": total,
        "albums": [
            {"id": album.id, "name": album.name, "photo_count": count}
            for album, count in rows
        ],
    }


async def _search_people(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.services.photo.service import PhotoService

    service = PhotoService(ctx.db, ctx.user)
    rows = await service.list_people()
    needle = (args.get("name") or "").strip().lower()
    people = [
        {"id": person.id, "name": person.name, "photo_count": photo_count}
        for person, _face_count, photo_count in rows
        if not needle or needle in person.name.lower()
    ]
    return {"total": len(people), "people": people}


async def _create_album(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.services.photo.service import PhotoService

    service = PhotoService(ctx.db, ctx.user)
    album = await service.create_album(
        {"name": args["name"], "description": args.get("description")}
    )
    return {"id": album.id, "name": album.name}


async def _analyze_photo(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.services.photo.service import PhotoService

    service = PhotoService(ctx.db, ctx.user)
    job = await service.request_analysis(int(args["photo_id"]))
    return {"job_id": job.id, "status": job.status}


async def _improve_photo(ctx: ToolContext, args: dict[str, Any]) -> Any:
    from app.services.photo.edits import create_edit
    from app.services.photo.service import PhotoService

    service = PhotoService(ctx.db, ctx.user)
    photo = await service.get_photo(int(args["photo_id"]))
    edit = await create_edit(
        ctx.db,
        photo,
        kind="auto_enhance",
        params={"enabled": True},
        name="Amélioration automatique",
        created_by=ctx.user.id,
    )
    return {"edit_id": edit.id, "width": edit.width, "height": edit.height}


async def _remove_object(ctx: ToolContext, args: dict[str, Any]) -> Any:
    raise NotImplementedError(
        "Suppression d'objet par IA : moteur non branché (architecture prête)"
    )


async def _remove_person(ctx: ToolContext, args: dict[str, Any]) -> Any:
    raise NotImplementedError(
        "Suppression de personne par IA : moteur non branché (architecture prête)"
    )


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="search_photos",
        description="Recherche des photos par texte, tag, personne ou favoris.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texte libre"},
                "tag": {"type": "string"},
                "person_id": {"type": "integer"},
                "favorite": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
        handler=_search_photos,
        permission="photos.view",
        access="read",
    ),
    ToolSpec(
        name="get_photo",
        description="Détaille une photo (métadonnées, tags, lieu).",
        input_schema={
            "type": "object",
            "properties": {"photo_id": {"type": "integer"}},
            "required": ["photo_id"],
        },
        handler=_get_photo,
        permission="photos.view",
        access="read",
    ),
    ToolSpec(
        name="list_albums",
        description="Liste les albums photo de l'utilisateur.",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
        },
        handler=_list_albums,
        permission="photos.view",
        access="read",
    ),
    ToolSpec(
        name="search_people",
        description="Liste ou filtre les personnes identifiées dans les photos.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
        handler=_search_people,
        permission="photos.view",
        access="read",
    ),
    ToolSpec(
        name="create_album",
        description="Crée un album photo.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name"],
        },
        handler=_create_album,
        permission="photos.albums.manage",
        access="write",
    ),
    ToolSpec(
        name="analyze_photo",
        description="(Re)lance l'analyse IA d'une photo en arrière-plan.",
        input_schema={
            "type": "object",
            "properties": {"photo_id": {"type": "integer"}},
            "required": ["photo_id"],
        },
        handler=_analyze_photo,
        permission="photos.analyze",
        access="write",
    ),
    ToolSpec(
        name="improve_photo",
        description="Applique l'amélioration automatique à une photo (nouvelle version).",
        input_schema={
            "type": "object",
            "properties": {"photo_id": {"type": "integer"}},
            "required": ["photo_id"],
        },
        handler=_improve_photo,
        permission="photos.edit",
        access="write",
        requires_confirmation=True,
    ),
    ToolSpec(
        name="remove_object",
        description="Supprime un objet gênant d'une photo par IA.",
        input_schema={
            "type": "object",
            "properties": {
                "photo_id": {"type": "integer"},
                "description": {"type": "string"},
            },
            "required": ["photo_id", "description"],
        },
        handler=_remove_object,
        permission="photos.edit",
        access="write",
        requires_confirmation=True,
    ),
    ToolSpec(
        name="remove_person",
        description="Supprime une personne d'une photo par IA.",
        input_schema={
            "type": "object",
            "properties": {
                "photo_id": {"type": "integer"},
                "person_id": {"type": "integer"},
            },
            "required": ["photo_id"],
        },
        handler=_remove_person,
        permission="photos.edit",
        access="write",
        requires_confirmation=True,
    ),
]

_registry: PhotoToolRegistry | None = None


def get_photo_tool_registry() -> PhotoToolRegistry:
    global _registry
    if _registry is None:
        registry = PhotoToolRegistry()
        for spec in SPECS:
            registry.register(spec)
        _registry = registry
    return _registry


def build_tool_context(db: AsyncSession, user: User) -> ToolContext:
    return ToolContext(db=db, user=user, settings=get_settings())
