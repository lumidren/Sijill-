from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .db import get_engine
from .routers import audit_log, auth, users

API_ROUTERS = [auth.router, users.router, audit_log.router]


def _optional_routers():
    """Routers added by later phases; imported lazily so the shell always starts."""
    import importlib

    out = []
    for name in ("catalog", "assessment", "checks", "posture", "reports", "settings_api",
                 "register", "obligations", "incidents", "dashboard"):
        try:
            mod = importlib.import_module(f".routers.{name}", __package__)
        except ModuleNotFoundError as e:
            if e.name and e.name.endswith(f"routers.{name}"):
                continue
            raise
        out.append(mod.router)
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_engine()
    sched = None
    if get_settings().scheduler_enabled and app.state.start_scheduler:
        try:
            from .scheduler import start_scheduler
        except ModuleNotFoundError:
            start_scheduler = None
        if start_scheduler:
            sched = start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


def create_app(start_scheduler: bool = True) -> FastAPI:
    app = FastAPI(title="PDPL-Ready", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.start_scheduler = start_scheduler
    for r in API_ROUTERS + _optional_routers():
        app.include_router(r)

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; script-src 'self'; frame-ancestors 'none'",
        )
        return resp

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    dist: Path = get_settings().frontend_dist
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "not_found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {"detail": "frontend not built - run scripts/start.ps1 or `npm run build` in frontend/"},
            status_code=503,
        )


app = create_app()
