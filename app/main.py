import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import auth, audit, buildings, dashboard, equipment, housing, maintenance, modules, admin, volunteer
from app.core.config import get_settings
from app.db.session import close_db, init_db
from app.modules import register_all_modules
from app.services.dashboard import register_dashboard_widgets
from app.services.rbac import seed_default_rbac

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW_SECONDS}seconds"] if settings.RATE_LIMIT_ENABLED else [],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    register_all_modules()
    register_dashboard_widgets()
    from app.db.session import get_db
    async for db in get_db():
        await seed_default_rbac(db)
        await _sync_module_statuses(db)
        break
    yield
    await close_db()


async def _sync_module_statuses(db):
    from sqlalchemy import select
    from app.models.module import Module as ModuleModel
    from app.modules import module_registry

    result = await db.execute(select(ModuleModel))
    db_modules = {m.code: m for m in result.scalars().all()}
    for code, reg_module in module_registry._modules.items():
        db_mod = db_modules.get(code)
        if db_mod:
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

SPA_PREFIXES = ("api/", "auth/", "admin/", "docs", "redoc", "openapi", "health", "css/", "js/", "modules/", "dashboard/")


@app.middleware("http")
async def spa_fallback_middleware(request: Request, call_next):
    response = await call_next(request)
    if (
        response.status_code in (401, 404, 422)
        and SPA_INDEX
        and request.headers.get("accept", "").startswith("text/html")
        and not any(request.url.path.startswith(f"/{p}") for p in SPA_PREFIXES)
    ):
        return FileResponse(SPA_INDEX)
    return response

app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(admin.router)
app.include_router(audit.router)
app.include_router(buildings.router)
app.include_router(dashboard.router)
app.include_router(equipment.router)
app.include_router(housing.router)
app.include_router(maintenance.router)
app.include_router(volunteer.router)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "src", "public")
SPA_INDEX = None
if os.path.exists(frontend_path):
    SPA_INDEX = os.path.join(frontend_path, "index.html")
    app.mount("/css", StaticFiles(directory=os.path.join(frontend_path, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_path, "js")), name="js")

    @app.get("/")
    async def serve_index():
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Frontend not built"}


@app.get("/{full_path:path}")
async def spa_catchall(full_path: str):
    if SPA_INDEX:
        return FileResponse(SPA_INDEX)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
