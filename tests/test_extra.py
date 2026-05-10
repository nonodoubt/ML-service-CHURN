"""Доп. тесты на менее покрытые места: batch, history, topup, admin, ML, security, limiter."""

import pytest

CHURN_BODY = {
    "ClientPeriod": 12, "MonthlySpending": 50.0, "TotalSpent": 600.0,
    "Sex": "Female", "IsSeniorCitizen": 0, "HasPartner": "No", "HasChild": "No",
    "HasPhoneService": "Yes", "HasMultiplePhoneNumbers": "No",
    "HasInternetService": "DSL",
    "HasOnlineSecurityService": "Yes", "HasOnlineBackup": "No",
    "HasDeviceProtection": "No", "HasTechSupportAccess": "Yes",
    "HasOnlineTV": "No", "HasMovieSubscription": "No",
    "HasContractPhone": "Month-to-month",
    "IsBillingPaperless": "Yes", "PaymentMethod": "Electronic check",
}


async def _register(client, email):
    r = await client.post("/auth/register", json={"email": email, "password": "secret123"})
    return r.json()["access_token"]


# ── Batch ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_batch_submits_and_charges(client):
    token = await _register(client, "batch@x.com")
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/ml/batch",
        json={"items": [CHURN_BODY, CHURN_BODY, CHURN_BODY]},
        headers=h,
    )
    assert r.status_code == 202
    me = (await client.get("/auth/me", headers=h)).json()
    # Списали 3 кредита
    assert me["total_credits"] == 20 - 3


@pytest.mark.asyncio
async def test_batch_validation_error(client):
    token = await _register(client, "batchv@x.com")
    h = {"Authorization": f"Bearer {token}"}
    r = await client.post("/ml/batch", json={"items": []}, headers=h)
    assert r.status_code == 422


# ── History ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_tasks(client):
    token = await _register(client, "hist@x.com")
    h = {"Authorization": f"Bearer {token}"}

    await client.post("/ml/submit", json=CHURN_BODY, headers=h)
    await client.post("/ml/submit", json=CHURN_BODY, headers=h)

    r = await client.get("/ml/tasks?limit=5", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2


# ── Top-up ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_topup(client):
    token = await _register(client, "topup@x.com")
    h = {"Authorization": f"Bearer {token}"}

    me_before = (await client.get("/auth/me", headers=h)).json()
    r = await client.post("/billing/topup", json={"amount": 100}, headers=h)
    assert r.status_code == 200

    me_after = (await client.get("/auth/me", headers=h)).json()
    # Добавилось ровно 100 на paid (бонусы не трогаем)
    assert me_after["paid_credits"] == me_before["paid_credits"] + 100


# ── Stats ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stats_me(client):
    token = await _register(client, "stats@x.com")
    h = {"Authorization": f"Bearer {token}"}

    await client.post("/ml/submit", json=CHURN_BODY, headers=h)
    r = await client.get("/stats/me", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total_predictions"] == 1
    assert body["total_credits_spent"] >= 1


# ── Admin ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_admin_endpoint_forbidden_for_user(client):
    token = await _register(client, "user@x.com")
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/admin/promo",
        json={"code": "X", "bonus_credits": 10},
        headers=h,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_promo(client):
    """Создаём админа руками в БД, потом дёргаем endpoint."""
    from app.db import session as session_module
    from app.db.models import User, UserRole, Tariff, TariffTier
    from app.core.security import hash_password, create_access_token
    from sqlalchemy import select

    async with session_module.async_session() as s:
        tariff = (await s.execute(select(Tariff).where(Tariff.tier == TariffTier.PRO))).scalar_one()
        admin = User(
            email="adm@x.com", hashed_password=hash_password("p"),
            role=UserRole.ADMIN, tariff_id=tariff.id,
        )
        s.add(admin)
        await s.commit()
        await s.refresh(admin)
        admin_id = str(admin.id)

    token = create_access_token(subject=admin_id, role="admin")
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/admin/promo",
        json={"code": "TESTCODE", "bonus_credits": 50},
        headers=h,
    )
    assert r.status_code == 201

    r2 = await client.get("/admin/promo", headers=h)
    assert r2.status_code == 200
    assert any(p["code"] == "TESTCODE" for p in r2.json())


# ── Security ─────────────────────────────────────────────────────────────
def test_password_hash_and_verify():
    from app.core.security import hash_password, verify_password
    h = hash_password("hello")
    assert verify_password("hello", h)
    assert not verify_password("wrong", h)


def test_decode_invalid_token_returns_none():
    from app.core.security import decode_token
    assert decode_token("not-a-jwt") is None


# ── Limiter (без реального redis) ────────────────────────────────────────
@pytest.mark.asyncio
async def test_invalid_token_returns_401(client):
    r = await client.get("/auth/me", headers={"Authorization": "Bearer bogus"})
    assert r.status_code == 401


# ── ML model ─────────────────────────────────────────────────────────────
def test_predict_with_string_total_spent():
    from app.ml.model import predict_one
    res = predict_one({
        "ClientPeriod": 0, "MonthlySpending": 0.0, "TotalSpent": " ",
        "Sex": "Male", "IsSeniorCitizen": 0,
        "HasPartner": "No", "HasChild": "No",
        "HasPhoneService": "No", "HasMultiplePhoneNumbers": "No phone service",
        "HasInternetService": "No",
        "HasOnlineSecurityService": "No internet service",
        "HasOnlineBackup": "No internet service",
        "HasDeviceProtection": "No internet service",
        "HasTechSupportAccess": "No internet service",
        "HasOnlineTV": "No internet service",
        "HasMovieSubscription": "No internet service",
        "HasContractPhone": "Two year",
        "IsBillingPaperless": "No", "PaymentMethod": "Mailed check",
    })
    assert "churn" in res
