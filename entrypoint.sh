#!/bin/bash
set -e

echo "=== Step 1: Create tables ==="
python -c "
import asyncio

# Импортируем ВСЕ модели явно — без этого Base.metadata их не видит
from app.db.models import (
    User, Tariff, PromoCode, PromoActivation,
    PredictionTask, CreditTransaction
)
from app.db.session import engine, Base

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables OK')

asyncio.run(main())
"

echo "=== Step 2: Seed tariffs, admin, promo ==="
python scripts/seed.py

echo "=== Step 3: Start API ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000