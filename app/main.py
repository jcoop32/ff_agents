"""
FastAPI application entrypoint.
Configured with database migrations, Redis connection pooling,
and strict Tailscale mesh network CORS headers.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.redis_client import init_redis_pool, close_redis
from app.core.database import engine, Base
from app.api.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown procedures."""
    logger.info("Starting up Gridiron AI multi-agent platform...")

    # Initialize Redis connection pool
    try:
        await init_redis_pool()
        logger.info("Connected to Redis pool.")
    except Exception as e:
        logger.warning("Redis connection pool offline (start via 'docker compose up -d redis'): %s", str(e))

    # Create tables if database reachable
    try:
        from app.core.database import init_db
        await init_db()
        logger.info("PostgreSQL database tables initialized successfully.")
    except Exception as e:
        logger.warning(
            "PostgreSQL is offline (start via 'docker compose up -d postgres' for persistence): %s. "
            "Running with live memory & ESPN API mode.",
            str(e)
        )

    # Background 24h ingestion worker
    import asyncio
    daily_task = None
    try:
        from app.pipelines.daily_scheduler import DailySchedulerService

        async def _daily_loop():
            # Initial run if >24h elapsed
            try:
                await DailySchedulerService.run_daily_ingestion_and_synthesis(force=False)
            except Exception as e:
                logger.warning("Initial daily sync check error: %s", str(e))
            while True:
                await asyncio.sleep(3600)
                try:
                    await DailySchedulerService.run_daily_ingestion_and_synthesis(force=False)
                except Exception as e:
                    logger.warning("Periodic daily sync error: %s", str(e))

        daily_task = asyncio.create_task(_daily_loop())
        logger.info("Daily 24h background ingestion worker initialized.")
    except Exception as e:
        logger.warning("Could not start daily background worker: %s", str(e))

    yield

    if daily_task:
        daily_task.cancel()

    logger.info("Shutting down Gridiron AI...")
    try:
        await close_redis()
    except Exception:
        pass
    try:
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous Fantasy Football Multi-Agent Platform & General Manager",
    lifespan=lifespan
)


class TailscaleCORSMiddleware(BaseHTTPMiddleware):
    """
    Dynamically permits CORS requests originating from any Tailscale mesh node
    (100.*.*.*), internal Kubernetes Pod CIDRs (10.*.*.*), or localhost.
    """
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        response = await call_next(request)

        if origin:
            # Check for Tailscale 100.x range or localhost
            if (
                origin.startswith("http://100.")
                or origin.startswith("https://100.")
                or "localhost" in origin
                or "127.0.0.1" in origin
            ):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "*"

        return response


# Apply CORS middlewares
app.add_middleware(TailscaleCORSMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(router)


@app.get("/")
async def root():
    return {
        "platform": settings.PROJECT_NAME,
        "league": "WA minus Josh",
        "format": f"{settings.LEAGUE_SIZE}-Team PPR (3-WR + 1-FLEX)",
        "team": "Team Cooper (#2)",
        "status": "online"
    }
