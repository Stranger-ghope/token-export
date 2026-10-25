from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
from gateway.config.settings import settings
from gateway.config.logging import configure_logging, log
from gateway.db.session import init_db
from gateway.api.v1.proxy import router as proxy_router
from gateway.api.v1.admin import router as admin_router
from gateway.api.v1.tools import router as tools_router
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
from sqlalchemy import text

REQUEST_COUNT = Counter("gateway_requests_total", "Total requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("gateway_request_latency_seconds", "Request latency", ["path"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Production safety checks
    if settings.app_env.lower() in ("prod", "production"):
        if not settings.admin_api_key or settings.admin_api_key == "dev-admin-key-change-me":
            raise RuntimeError("ADMIN_API_KEY must be set in production")
        if settings.jwt_secret == "change-me-in-prod-please-32bytes-min":
            raise RuntimeError("JWT_SECRET must be changed in production")
        if settings.cors_origins.strip() == "*":
            log.warning("cors_wildcard_in_prod")
    await init_db()
    log.info("gateway_started", env=settings.app_env, port=settings.port)
    yield
    log.info("gateway_stopped")
    try:
        from gateway.db.session import get_engine
        eng = get_engine()
        if eng is not None:
            await eng.dispose()
    except Exception:
        pass


app = FastAPI(
    title="AI Token Export / Routing Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow_origins=["*"] with credentials is invalid; only enable credentials
# when origins are explicit.
_raw_origins = settings.cors_origins.strip()
if _raw_origins == "*":
    _origins = ["*"]
    _creds = False
else:
    _origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    _creds = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    REQUEST_LATENCY.labels(request.url.path).observe(time.time() - start)
    response.headers["x-request-id"] = getattr(request.state, "request_id", "")
    return response


@app.middleware("http")
async def body_size_limit(request: Request, call_next):
    if settings.max_request_body_bytes and request.method in ("POST", "PUT", "PATCH"):
        cl = request.headers.get("content-length")
        if cl and int(cl) > settings.max_request_body_bytes:
            return JSONResponse(status_code=413, content={"error": "request body too large"})
    return await call_next(request)

app.include_router(proxy_router)
app.include_router(admin_router)
app.include_router(tools_router)


@app.get("/health")
async def health():
    db_ok = True
    try:
        from gateway.db.session import get_session_factory
        sf = get_session_factory()
        if sf is not None:
            async with sf() as session:
                await session.execute(text("SELECT 1"))
    except Exception as e:
        db_ok = False
        log.warning("health_db_fail", error=str(e))
    return {"status": "ok" if db_ok else "degraded", "env": settings.app_env, "db": db_ok}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("unhandled_exception", error=str(exc), path=str(request.url))
    return JSONResponse(status_code=500, content={"error": "internal server error"})


# Serve the built admin console (frontend/dist) when it exists, so the gateway
# exposes the UI and the API on a single origin. Registered last so every API
# route registered above wins over this static catch-all.
_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="console")
