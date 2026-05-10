"""Тесты промокодов."""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.db import session as session_module
from app.db.models import PromoCode, PromoType


async def _create_promo(code, bonus=100, max_act=None, valid_until=None):
    async with session_module.async_session() as s:
        p = PromoCode(
            code=code, promo_type=PromoType.FIXED,
            bonus_credits=bonus, max_activations=max_act,
            valid_until=valid_until, is_active=True,
        )
        s.add(p)
        await s.commit()
        return p


async def _register_and_login(client, email="promo@x.com"):
    r = await client.post("/auth/register", json={"email": email, "password": "secret123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_activate_promo_adds_bonus(client):
    await _create_promo("WELCOME100", bonus=100)
    token = await _register_and_login(client, "p1@x.com")
    headers = {"Authorization": f"Bearer {token}"}

    # До активации
    me0 = (await client.get("/auth/me", headers=headers)).json()
    bonus_before = me0["bonus_credits"]

    r = await client.post("/promo/activate", json={"code": "WELCOME100"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["bonus_credits_added"] == 100

    me1 = (await client.get("/auth/me", headers=headers)).json()
    assert me1["bonus_credits"] == bonus_before + 100


@pytest.mark.asyncio
async def test_cannot_activate_twice(client):
    await _create_promo("ONESHOT", bonus=50)
    token = await _register_and_login(client, "p2@x.com")
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post("/promo/activate", json={"code": "ONESHOT"}, headers=headers)
    assert r1.status_code == 200

    r2 = await client.post("/promo/activate", json={"code": "ONESHOT"}, headers=headers)
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_expired_promo(client):
    await _create_promo(
        "EXPIRED", bonus=10,
        valid_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    token = await _register_and_login(client, "p3@x.com")
    r = await client.post(
        "/promo/activate", json={"code": "EXPIRED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_max_activations_limit(client):
    await _create_promo("LIMITED", bonus=5, max_act=1)
    t1 = await _register_and_login(client, "u1@x.com")
    t2 = await _register_and_login(client, "u2@x.com")

    r1 = await client.post("/promo/activate", json={"code": "LIMITED"},
                           headers={"Authorization": f"Bearer {t1}"})
    assert r1.status_code == 200

    r2 = await client.post("/promo/activate", json={"code": "LIMITED"},
                           headers={"Authorization": f"Bearer {t2}"})
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_unknown_promo(client):
    token = await _register_and_login(client, "p4@x.com")
    r = await client.post("/promo/activate", json={"code": "NONEXISTENT"},
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
