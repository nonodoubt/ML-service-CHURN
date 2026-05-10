"""Создаёт админа и промокод WELCOME50.

Запускается автоматически из docker-compose после обучения модели.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import (
    User, UserRole, Tariff, TariffTier, PromoCode, PromoType,
)
from app.db.session import async_session


async def main():
    async with async_session() as s:
        # Админ — email без .local, чтобы Pydantic не ругался
        admin_email = os.getenv("ADMIN_EMAIL", "admin@gmail.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin12345")

        existing = (await s.execute(select(User).where(User.email == admin_email))).scalar_one_or_none()
        if existing is None:
            tariff = (await s.execute(
                select(Tariff).where(Tariff.tier == TariffTier.PRO)
            )).scalar_one_or_none()
            if tariff is None:
                print("[seed] Tariffs not found — run app first")
                return

            admin = User(
                email=admin_email,
                hashed_password=hash_password(admin_password),
                role=UserRole.ADMIN,
                tariff_id=tariff.id,
                paid_credits=10_000,
                bonus_credits=1_000,
            )
            s.add(admin)
            print(f"[seed] Admin created: {admin_email} / {admin_password}")
        else:
            print(f"[seed] Admin already exists: {admin_email}")

        # Промокод WELCOME50
        if (await s.execute(select(PromoCode).where(PromoCode.code == "WELCOME50"))).scalar_one_or_none() is None:
            promo = PromoCode(
                code="WELCOME50",
                promo_type=PromoType.FIXED,
                bonus_credits=50,
                max_activations=1000,
                valid_until=datetime.now(timezone.utc) + timedelta(days=365),
            )
            s.add(promo)
            print("[seed] Created promo WELCOME50 (+50 credits)")

        await s.commit()
        print("[seed] Done")


if __name__ == "__main__":
    asyncio.run(main())
