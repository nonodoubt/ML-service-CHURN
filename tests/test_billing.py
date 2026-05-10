"""Тесты биллинга — критичная часть, потому подробно."""

import pytest
from sqlalchemy import select

from app.db import session as session_module
from app.db.models import User, Tariff, TariffTier, CreditTransaction
from app.services import billing
from app.core.security import hash_password


async def _make_user(paid=0, bonus=0) -> User:
    async with session_module.async_session() as s:
        res = await s.execute(select(Tariff).where(Tariff.tier == TariffTier.FREE))
        tariff = res.scalar_one()
        u = User(
            email=f"x{paid}{bonus}@x.com",
            hashed_password=hash_password("p"),
            tariff_id=tariff.id,
            paid_credits=paid,
            bonus_credits=bonus,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u, ["tariff"])
        return u


@pytest.mark.asyncio
async def test_charge_uses_bonus_first(client):
    user = await _make_user(paid=10, bonus=5)
    async with session_module.async_session() as s:
        u = (await s.execute(select(User).where(User.id == user.id))).scalar_one()
        bonus_used, paid_used = await billing.charge_credits(s, u, 7, "test")
        await s.commit()
        # Сначала должны были потратить все 5 бонусов, потом 2 paid
        assert bonus_used == 5
        assert paid_used == 2
        assert u.bonus_credits == 0
        assert u.paid_credits == 8


@pytest.mark.asyncio
async def test_charge_insufficient_raises(client):
    user = await _make_user(paid=2, bonus=1)
    async with session_module.async_session() as s:
        u = (await s.execute(select(User).where(User.id == user.id))).scalar_one()
        with pytest.raises(ValueError):
            await billing.charge_credits(s, u, 10, "test")
        # ничего не должно было измениться
        assert u.paid_credits == 2 and u.bonus_credits == 1


@pytest.mark.asyncio
async def test_refund_returns_to_correct_buckets(client):
    user = await _make_user(paid=10, bonus=5)
    async with session_module.async_session() as s:
        u = (await s.execute(select(User).where(User.id == user.id))).scalar_one()
        bonus_used, paid_used = await billing.charge_credits(s, u, 7, "reserve")
        await s.commit()

        await billing.refund_credits(s, u, bonus_used, paid_used, "refund")
        await s.commit()

        assert u.paid_credits == 10
        assert u.bonus_credits == 5


@pytest.mark.asyncio
async def test_charge_creates_transaction_log(client):
    user = await _make_user(paid=5, bonus=5)
    async with session_module.async_session() as s:
        u = (await s.execute(select(User).where(User.id == user.id))).scalar_one()
        await billing.charge_credits(s, u, 3, "reserve")
        await s.commit()

        res = await s.execute(select(CreditTransaction).where(CreditTransaction.user_id == u.id))
        txs = res.scalars().all()
        # Только запись о списании (signup-бонуса не было — мы создавали user руками)
        charge_txs = [t for t in txs if t.reason == "reserve"]
        assert len(charge_txs) == 1
        assert charge_txs[0].bonus_delta == -3
        assert charge_txs[0].paid_delta == 0
