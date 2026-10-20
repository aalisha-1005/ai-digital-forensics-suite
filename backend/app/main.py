from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__, config, migrations
from .routers import auth, cases, evidence, system, workspace


@asynccontextmanager
async def lifespan(app):
    migrations.run()
    yield


app = FastAPI(title="AI-Based Digital Forensics Investigation Suite", version=__version__, lifespan=lifespan,
              description="Offline, defensive forensic workstation API. Interactive docs at /docs.")
app.add_middleware(CORSMiddleware, allow_origin_regex=".*", allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                         "Cache-Control": "no-store"})
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # never leak internals; details stay in server logs
    import logging
    logging.getLogger("dfis").exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


for r in (auth.router, cases.router, evidence.router, workspace.router, system.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

DIST_DIR = config.BASE_DIR.parent / "frontend" / "dist"
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_root():
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        file_path = DIST_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(DIST_DIR / "index.html")


