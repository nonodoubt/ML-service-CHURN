"""Тесты регистрации, логина, /me."""

import pytest


CHURN_BODY = {
    "ClientPeriod": 55, "MonthlySpending": 19.5, "TotalSpent": 1026.35,
    "Sex": "Male", "IsSeniorCitizen": 0, "HasPartner": "Yes", "HasChild": "Yes",
    "HasPhoneService": "Yes", "HasMultiplePhoneNumbers": "No",
    "HasInternetService": "No",
    "HasOnlineSecurityService": "No internet service",
    "HasOnlineBackup": "No internet service",
    "HasDeviceProtection": "No internet service",
    "HasTechSupportAccess": "No internet service",
    "HasOnlineTV": "No internet service",
    "HasMovieSubscription": "No internet service",
    "HasContractPhone": "One year",
    "IsBillingPaperless": "No", "PaymentMethod": "Mailed check",
}


@pytest.mark.asyncio
async def test_register_returns_token(client):
    r = await client.post("/auth/register", json={
        "email": "a@b.com", "password": "secret123",
    })
    assert r.status_code == 201
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    body = {"email": "dup@b.com", "password": "secret123"}
    r1 = await client.post("/auth/register", json=body)
    assert r1.status_code == 201
    r2 = await client.post("/auth/register", json=body)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={"email": "u@x.com", "password": "rightone"})
    r = await client.post("/auth/login", json={"email": "u@x.com", "password": "wrongone"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    r = await client.post("/auth/register", json={"email": "me@x.com", "password": "qwerty1"})
    token = r.json()["access_token"]
    r2 = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["email"] == "me@x.com"
    # При регистрации должны были начислиться signup-бонусы
    assert body["bonus_credits"] >= 1


@pytest.mark.asyncio
async def test_me_without_token(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401
