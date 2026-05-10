"""Точка входа FastAPI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.auth import router as auth_router
from app.api.predictions import router as predictions_router
from app.api.promo import router as promo_router
from app.core.limiter import close_redis
from app.db.session import Base
from app.db import session as db_session
from app.ml.model import load_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Старт: создаём таблицы (для прода — Alembic), сидим тарифы, грузим модель
    async with db_session.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_tariffs()
    load_model()
    logger.info("Service is ready")

    yield

    await close_redis()
    await db_session.engine.dispose()


app = FastAPI(
    title="Churn Prediction Service",
    version="1.0.0",
    description="Сервис предсказания оттока клиентов с биллингом, JWT и Celery",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Метрики /metrics для Prometheus
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(auth_router)
app.include_router(predictions_router)
app.include_router(promo_router)


# ─────────────────────────────────────────────────────────────────────────
# Сиды: тарифы при первом запуске
# ─────────────────────────────────────────────────────────────────────────
async def _seed_tariffs():
    from sqlalchemy import select
    from app.db.session import async_session
    from app.db.models import Tariff, TariffTier

    async with async_session() as session:
        existing = await session.execute(select(Tariff))
        if existing.scalars().first():
            return
        session.add_all([
            Tariff(tier=TariffTier.FREE,  rate_limit=10,  rate_window=60, max_concurrent=1,  cost_per_prediction=1),
            Tariff(tier=TariffTier.BASIC, rate_limit=60,  rate_window=60, max_concurrent=5,  cost_per_prediction=1),
            Tariff(tier=TariffTier.PRO,   rate_limit=300, rate_window=60, max_concurrent=20, cost_per_prediction=1),
        ])
        await session.commit()
        logger.info("Tariffs seeded")
