from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from gateway.config.settings import settings
from gateway.config.logging import configure_logging, log
from gateway.db.session import init_db
from gateway.api.v1.proxy import router as proxy_router
from gateway.api.v1.admin import router as admin_router
from gateway.api.v1.tools import router as tools_router
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

REQUEST_COUNT = Counter("gateway_requests_total", "Total requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("gateway_request_latency_seconds", "Request latency", ["path"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await init_db()
    log.info("gateway_started", env=settings.app_env, port=settings.port)
    yield
    log.info("gateway_stopped")


app = FastAPI(
    title="AI Token Export / Routing Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


app.include_router(proxy_router)
app.include_router(admin_router)
app.include_router(tools_router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("unhandled_exception", error=str(exc), path=str(request.url))
    return JSONResponse(status_code=500, content={"error": "internal server error"})
