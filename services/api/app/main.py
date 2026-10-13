from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from sqlalchemy import text

from app.db import get_engine
from app.routers import admin, auth, core

app = FastAPI(
    title="Fault Sigma API",
    version="0.1.0",
    # Swagger UI loads assets from a public CDN, which the no-third-party rule forbids.
    # The schema stays available at /openapi.json for client generation.
    docs_url=None,
    redoc_url=None,
)

_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-origin",
}


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(core.router)
app.include_router(admin.router)
