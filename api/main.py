"""FastAPI application entrypoint.

Run from inside the api/ directory:
    uvicorn main:app --reload
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.redis import close_redis, get_redis
from db.pool import close_pool, get_pool
from routers.auth import router as auth_router
from routers.chat import router as chat_router
from routers.conversations import router as conversations_router
from routers.customers import router as customers_router
from routers.eval import router as eval_router
from routers.issues import router as issues_router
from routers.next_actions import router as next_actions_router
from routers.usage import router as usage_router

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise the Postgres pool and Redis client on startup, close on shutdown."""
    await get_pool()
    get_redis()
    yield
    await close_pool()
    await close_redis()


app = FastAPI(title="Acme Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each request's method, path, status, and latency as JSON."""
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=round(latency_ms, 2),
    )
    return response


app.include_router(auth_router, prefix="/auth")
app.include_router(chat_router, prefix="/chat")
app.include_router(conversations_router, prefix="/conversations")
app.include_router(customers_router, prefix="/customers")
app.include_router(eval_router, prefix="/eval")
app.include_router(issues_router, prefix="/issues")
app.include_router(next_actions_router, prefix="/next-actions")
app.include_router(usage_router, prefix="/usage")
