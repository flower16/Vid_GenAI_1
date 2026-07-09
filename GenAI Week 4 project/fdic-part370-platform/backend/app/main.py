"""FastAPI entrypoint with CORS, OpenTelemetry, and LangSmith tracing."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .core.config import settings

logging.basicConfig(level=settings.log_level)

# Enable LangSmith tracing if configured
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    # Allow Replit-hosted preview/deploy origins (*.repl.co, *.replit.dev).
    allow_origin_regex=r"https://.*\.(repl\.co|replit\.dev|replit\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


def _mount_frontend() -> None:
    """Serve the built frontend (frontend/dist) same-origin when present.

    On Replit the app runs as a single web process: `start.sh` builds the
    frontend, then this mount serves it at `/` while the API stays under
    `/api/*` and `/health` (registered above, so they win over this catch-all).
    In local dev the dist folder is absent and Vite serves the UI on :5173.
    """
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
        logging.getLogger(__name__).info("Serving frontend from %s", dist)


_mount_frontend()


def _init_otel() -> None:  # pragma: no cover - external dep
    """Wire OpenTelemetry auto-instrumentation for FastAPI."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        logging.getLogger(__name__).info("OTel not enabled: %s", exc)


_init_otel()
