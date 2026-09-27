import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import auth, audit, buildings, dashboard, equipment, housing, maintenance, modules, admin, volunteer, sport, administrative, agenda, notifications
from app.core.config import get_settings
from app.db.session import close_db, init_db
from app.modules import register_all_modules
from app.services.ai_gateway.config_store import apply_from_db as apply_ai_settings_from_db
from app.services.dashboard import register_dashboard_widgets
from app.services.notifications.config_store import apply_vapid_from_db
from app.services.rbac import seed_default_rbac

settings = get_settings()
garmin_sync_task = None
ad_sync_task = None
sport_analysis_task = None

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW_SECONDS}seconds"] if settings.RATE_LIMIT_ENABLED else [],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global garmin_sync_task, ad_sync_task
    await init_db()
    register_all_modules()
    register_dashboard_widgets()
    from app.db.session import get_db
    async for db in get_db():
        await seed_default_rbac(db)
        await _sync_module_statuses(db)
        await apply_ai_settings_from_db(db)
        await apply_vapid_from_db(db)
        break
    garmin_sync_task = asyncio.create_task(_garmin_sync_loop())
    ad_sync_task = asyncio.create_task(_ad_sync_loop())
    sport_analysis_task = asyncio.create_task(_sport_analysis_loop())
    yield
    if sport_analysis_task:
        sport_analysis_task.cancel()
        try:
            await sport_analysis_task
        except asyncio.CancelledError:
            pass
    if ad_sync_task:
        ad_sync_task.cancel()
        try:
            await ad_sync_task
        except asyncio.CancelledError:
            pass
    if garmin_sync_task:
        garmin_sync_task.cancel()
        try:
            await garmin_sync_task
        except asyncio.CancelledError:
            pass
    await close_db()


async def _garmin_sync_loop() -> None:
    from app.db.session import get_db
    from app.services.garmin import SportGarminConnectService

    while True:
        try:
            async for db in get_db():
                await SportGarminConnectService(db).sync_all_connections()
                break
        except asyncio.CancelledError:
            raise
        except Exception:
            # Garmin outages must not affect application startup or other modules.
            pass
        await asyncio.sleep(900)


async def _ad_sync_loop() -> None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db.session import get_db
    from app.models.ad_integration import ADConfig
    from app.services.ad import DatabaseADService

    # Synchro automatique chaque nuit a 03:00 (Europe/Paris).
    tz = ZoneInfo("Europe/Paris")
    while True:
        try:
            now = datetime.now(tz)
            next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())

            async for db in get_db():
                configs = (
                    await db.execute(
                        select(ADConfig)
                        .options(selectinload(ADConfig.group_mappings))
                        .where(ADConfig.is_active.is_(True))
                    )
                ).scalars().all()
                for config in configs:
                    try:
                        print(f"[AD-SYNC] Synchro automatique nocturne — config {config.id} ({config.name})")
                        await DatabaseADService(db).sync_users(config)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        print(f"[AD-SYNC] Synchro automatique en echec (config {config.id}): {exc}")
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Une erreur de la boucle ne doit pas tuer l'application.
            print(f"[AD-SYNC] Boucle de synchro automatique: {exc}")


async def _sport_analysis_loop() -> None:
    from app.db.session import get_db
    from app.services.sport_analysis_service import run_sport_analysis_cycle

    # Analyses sportives automatiques (matin / soir / activité).
    # L'idempotence en base permet de relancer le cycle fréquemment.
    while True:
        try:
            async for db in get_db():
                await run_sport_analysis_cycle(db)
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Une analyse en echec ne doit jamais tuer l'application.
            print(f"[SPORT-ANALYSIS] Cycle en echec: {exc}")
        await asyncio.sleep(60)


async def _sync_module_statuses(db):
    from sqlalchemy import select
    from app.models.module import Module as ModuleModel
    from app.modules import module_registry

    result = await db.execute(select(ModuleModel))
    db_modules = {m.code: m for m in result.scalars().all()}
    for code, reg_module in module_registry._modules.items():
        db_mod = db_modules.get(code)
        if db_mod:
            db_mod.name = reg_module.info.name
            db_mod.description = reg_module.info.description
            reg_module.info.status = db_mod.status
        else:
            new_mod = ModuleModel(
                code=code,
                name=reg_module.info.name,
                description=reg_module.info.description,
                icon=reg_module.info.icon,
                order=reg_module.info.order,
                status=reg_module.info.status,
                version=reg_module.info.version,
                route_path=reg_module.info.route_path,
                component_path=reg_module.info.component_path,
                required_permissions=reg_module.info.required_permissions,
                is_core=reg_module.info.is_core,
            )
            db.add(new_mod)
    await db.commit()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}

SPA_PREFIXES = ("api/", "auth/", "admin/", "docs", "redoc", "openapi", "health", "css/", "js/", "modules/", "dashboard/", "notifications/")


def _is_spa_navigation(request: Request) -> bool:
    return (
        request.method == "GET"
        and SPA_INDEX
        and request.headers.get("accept", "").startswith("text/html")
        and not any(request.url.path.startswith(f"/{prefix}") for prefix in SPA_PREFIXES)
        and not request.url.path.startswith("/housing/public/")
    )


@app.middleware("http")
async def spa_fallback_middleware(request: Request, call_next):
    if _is_spa_navigation(request):
        return FileResponse(SPA_INDEX)

    response = await call_next(request)
    if (
        response.status_code in (401, 404, 422)
        and _is_spa_navigation(request)
    ):
        return FileResponse(SPA_INDEX)
    return response

app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(admin.router)
app.include_router(admin.settings_router)
app.include_router(audit.router)
app.include_router(buildings.router)
app.include_router(dashboard.router)
app.include_router(equipment.router)
app.include_router(housing.router)
app.include_router(maintenance.router)
app.include_router(volunteer.router)
app.include_router(sport.router)
app.include_router(notifications.router)
app.include_router(administrative.router)
app.include_router(agenda.router)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "src", "public")
SPA_INDEX = None
if os.path.exists(frontend_path):
    SPA_INDEX = os.path.join(frontend_path, "index.html")
    app.mount("/css", StaticFiles(directory=os.path.join(frontend_path, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_path, "js")), name="js")
    icons_dir = os.path.join(frontend_path, "icons")
    if os.path.isdir(icons_dir):
        app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

    @app.get("/")
    async def serve_index():
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Frontend not built"}

    @app.get("/manifest.webmanifest")
    async def serve_web_manifest():
        # Manifest PWA : MIME explicite (le catchall SPA renverrait index.html).
        manifest_path = os.path.join(frontend_path, "manifest.webmanifest")
        if os.path.exists(manifest_path):
            return FileResponse(manifest_path, media_type="application/manifest+json")
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    @app.get("/sw.js")
    async def serve_service_worker():
        # Service worker des notifications telephone : doit etre servi avec
        # un type MIME JavaScript (le catchall SPA renverrait index.html).
        sw_path = os.path.join(frontend_path, "sw.js")
        if os.path.exists(sw_path):
            return FileResponse(sw_path, media_type="application/javascript")
        return JSONResponse(status_code=404, content={"detail": "Not Found"})


@app.get("/{full_path:path}")
async def spa_catchall(full_path: str):
    if SPA_INDEX:
        return FileResponse(SPA_INDEX)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
