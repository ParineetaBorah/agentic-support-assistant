"""FastAPI application entrypoint.

Run from inside the api/ directory:
    uvicorn main:app --reload
"""

from __future__ import annotations

import time
import traceback
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
        structlog.contextvars.merge_contextvars,
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
    """Log each request as JSON (method, path, status, latency); log unhandled errors with a stack trace.

    A request_id correlates the log line with the response (X-Request-ID header,
    and the body of a 500). HTTPException (401/403/404) is already turned into a
    response by Starlette's inner handler, so only genuine unhandled errors are
    caught here and surfaced as a 500.
    """
    request_id = str(uuid.uuid4())
    # Bind to the request context so request_id is injected into EVERY log line
    # emitted while handling this request — including the agent's tool_error logs —
    # without threading it through the call stack (merge_contextvars processor).
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "unhandled_exception",
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
            error_message=str(exc),
            latency_ms=round(latency_ms, 2),
            stack_trace=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    latency_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=round(latency_ms, 2),
    )
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(auth_router, prefix="/auth")
app.include_router(chat_router, prefix="/chat")
app.include_router(conversations_router, prefix="/conversations")
app.include_router(customers_router, prefix="/customers")
app.include_router(eval_router, prefix="/eval")
app.include_router(issues_router, prefix="/issues")
app.include_router(next_actions_router, prefix="/next-actions")
app.include_router(usage_router, prefix="/usage")
