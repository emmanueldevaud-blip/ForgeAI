import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import auth, buildings, modules, todos, admin
from app.core.config import get_settings
from app.db.session import close_db, init_db
from app.modules import register_all_modules
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
    from app.db.session import get_db
    async for db in get_db():
        await seed_default_rbac(db)
        break
    yield
    await close_db()


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

app.include_router(auth.router)
app.include_router(todos.router)
app.include_router(modules.router)
app.include_router(admin.router)
app.include_router(buildings.router)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "src", "public")
if os.path.exists(frontend_path):
    app.mount("/css", StaticFiles(directory=os.path.join(frontend_path, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_path, "js")), name="js")

    @app.get("/")
    async def serve_index():
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Frontend not built"}

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("auth/") or full_path.startswith("admin/") or full_path.startswith("docs") or full_path.startswith("redoc") or full_path.startswith("openapi") or full_path.startswith("health") or full_path == "health" or full_path.startswith("css/") or full_path.startswith("js/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not found"}, status_code=404)
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Frontend not built"}