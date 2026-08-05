import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ads, chat

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


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
