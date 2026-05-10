"""Конфиг pytest + общие фикстуры."""

import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DATABASE_URL_SYNC"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["MODEL_PATH"] = "/nonexistent"

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.db.session import Base
from app.db import session as session_module


@pytest_asyncio.fixture
async def client(monkeypatch):
    """Полная инициализация в одной фикстуре — БД + моки + httpx-клиент."""

    # ── 1. Свежая БД на тест ─────────────────────────────────
    db_file = tempfile.mktemp(suffix=".db")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}", poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_module.engine = engine
    session_module.async_session = async_sessionmaker(engine, expire_on_commit=False)

    # ── 2. Моки Redis ────────────────────────────────────────
    from app.core import limiter

    async def fake_check(*a, **kw): return True
    async def fake_acquire(*a, **kw): return True
    async def fake_release(*a, **kw): return None

    class FakeRedis:
        async def ping(self): return True
        async def close(self): return None

    async def fake_get_redis(): return FakeRedis()

    monkeypatch.setattr(limiter, "check_rate_limit", fake_check)
    monkeypatch.setattr(limiter, "acquire_concurrent_slot", fake_acquire)
    monkeypatch.setattr(limiter, "release_concurrent_slot", fake_release)
    monkeypatch.setattr(limiter, "get_redis", fake_get_redis)

    from app.api import predictions as preds_mod
    monkeypatch.setattr(preds_mod, "check_rate_limit", fake_check)
    monkeypatch.setattr(preds_mod, "acquire_concurrent_slot", fake_acquire)
    monkeypatch.setattr(preds_mod, "release_concurrent_slot", fake_release)
    monkeypatch.setattr(preds_mod, "get_redis", fake_get_redis)

    # ── 3. Моки Celery ───────────────────────────────────────
    from app.tasks import worker

    class FakeAsyncResult:
        id = "fake-task-id"

    def fake_delay(*a, **kw): return FakeAsyncResult()

    monkeypatch.setattr(worker.run_prediction, "delay", fake_delay)
    monkeypatch.setattr(worker.run_batch_prediction, "delay", fake_delay)

    # ── 4. Сиды тарифов ──────────────────────────────────────
    from app.db.models import Tariff, TariffTier
    async with session_module.async_session() as s:
        s.add_all([
            Tariff(tier=TariffTier.FREE,  rate_limit=10,  rate_window=60, max_concurrent=1,  cost_per_prediction=1),
            Tariff(tier=TariffTier.BASIC, rate_limit=60,  rate_window=60, max_concurrent=5,  cost_per_prediction=1),
            Tariff(tier=TariffTier.PRO,   rate_limit=300, rate_window=60, max_concurrent=20, cost_per_prediction=1),
        ])
        await s.commit()

    # ── 5. App без lifespan ──────────────────────────────────
    from fastapi import FastAPI
    from app.api.auth import router as auth_router
    from app.api.predictions import router as predictions_router
    from app.api.promo import router as promo_router

    test_app = FastAPI()
    test_app.include_router(auth_router)
    test_app.include_router(predictions_router)
    test_app.include_router(promo_router)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    try:
        os.unlink(db_file)
    except FileNotFoundError:
        pass
