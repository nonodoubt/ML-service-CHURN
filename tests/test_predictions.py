"""Тесты пайплайна предсказания: проверки, резерв, статус."""

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


async def _register(client, email):
    r = await client.post("/auth/register", json={"email": email, "password": "secret123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "db" in body and "redis" in body and "model" in body


@pytest.mark.asyncio
async def test_submit_requires_auth(client):
    r = await client.post("/ml/submit", json=CHURN_BODY)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_submit_charges_credit(client):
    token = await _register(client, "pred1@x.com")
    h = {"Authorization": f"Bearer {token}"}

    me_before = (await client.get("/auth/me", headers=h)).json()
    r = await client.post("/ml/submit", json=CHURN_BODY, headers=h)
    assert r.status_code == 202

    me_after = (await client.get("/auth/me", headers=h)).json()
    # 1 кредит должен был быть зарезервирован (списан с бонуса)
    assert me_after["total_credits"] == me_before["total_credits"] - 1


@pytest.mark.asyncio
async def test_submit_returns_402_when_no_credits(client):
    token = await _register(client, "pred2@x.com")
    h = {"Authorization": f"Bearer {token}"}

    # Тратим все кредиты подряд (signup_bonus = 20)
    for _ in range(25):
        r = await client.post("/ml/submit", json=CHURN_BODY, headers=h)
        if r.status_code == 402:
            return
    pytest.fail("Ожидали 402 после исчерпания баланса")


@pytest.mark.asyncio
async def test_submit_validates_input(client):
    token = await _register(client, "pred3@x.com")
    h = {"Authorization": f"Bearer {token}"}

    bad = dict(CHURN_BODY)
    bad["Sex"] = "Other"     # не из enum
    r = await client.post("/ml/submit", json=bad, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_get_task_returns_pending(client):
    token = await _register(client, "pred4@x.com")
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post("/ml/submit", json=CHURN_BODY, headers=h)
    task_id = r.json()["task_id"]

    r2 = await client.get(f"/ml/tasks/{task_id}", headers=h)
    assert r2.status_code == 200
    assert r2.json()["status"] in ("pending", "processing", "completed")


@pytest.mark.asyncio
async def test_cannot_get_others_task(client):
    t1 = await _register(client, "owner@x.com")
    t2 = await _register(client, "intruder@x.com")

    r = await client.post("/ml/submit", json=CHURN_BODY,
                          headers={"Authorization": f"Bearer {t1}"})
    task_id = r.json()["task_id"]

    r2 = await client.get(f"/ml/tasks/{task_id}",
                          headers={"Authorization": f"Bearer {t2}"})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_predict_one_runs_with_stub_model(client):
    """Без реального model.joblib используется stub, predict_one работает."""
    from app.ml.model import predict_one
    res = predict_one({
        "ClientPeriod": 1, "MonthlySpending": 50.0, "TotalSpent": 50.0,
        "Sex": "Male", "IsSeniorCitizen": 0,
        "HasPartner": "No", "HasChild": "No",
        "HasPhoneService": "Yes", "HasMultiplePhoneNumbers": "No",
        "HasInternetService": "Fiber optic",
        "HasOnlineSecurityService": "No", "HasOnlineBackup": "No",
        "HasDeviceProtection": "No", "HasTechSupportAccess": "No",
        "HasOnlineTV": "No", "HasMovieSubscription": "No",
        "HasContractPhone": "Month-to-month",
        "IsBillingPaperless": "Yes", "PaymentMethod": "Electronic check",
    })
    assert "churn" in res and "reliable" in res and "probability_churn" in res
    assert res["reliable"] in (0, 1)
