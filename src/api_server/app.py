"""FastAPI app wiring `/dynamic` (execution), `/static` (curated docs), and `/components`
(persisted checklist) - Module 3.

Run standalone via `python -m src.api_server` (see `__main__.py`); this module only builds the
app object, so it's also importable directly by tests (`fastapi.testclient.TestClient`).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import playwright_runtime
from .components import router as components_router
from .dynamic import router as dynamic_router
from .static_docs import router as static_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    playwright_runtime.close_scraper()


app = FastAPI(title="Pragma API Server", lifespan=lifespan)
app.include_router(dynamic_router)
app.include_router(static_router)
app.include_router(components_router)
