import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ads, chat

log = logging.getLogger(__name__)

app = FastAPI(
    title="Ad Aggregator API",
    description="Мулти-агентски систем за агрегирање огласи за техника",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_extra = os.getenv("ALLOWED_ORIGINS", "")
_origins = ["http://localhost:5173"] + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ads.router)
app.include_router(chat.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Registered handlers run inside CORSMiddleware, so the response still
    # gets CORS headers — unlike an uncaught exception, which Starlette's
    # ServerErrorMiddleware turns into a header-less 500 that the browser
    # reports as a misleading "blocked by CORS policy" error.
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
