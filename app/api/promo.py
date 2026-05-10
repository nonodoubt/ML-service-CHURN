"""Промокоды и админ-эндпоинты."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.api.schemas import (
    PromoActivateRequest, PromoActivateResponse, PromoCreateRequest,
    TopUpRequest, StatsResponse,
)
from app.db.models import (
    User, PromoCode, PromoType, PredictionTask, TaskStatus, CreditTransaction,
)
from app.db.session import get_db
from app.services import billing
from app.services.promo import activate_promo, PromoError

router = APIRouter(tags=["promo"])


# ─────────────────────────────────────────────────────────────────────────
# Активация промокода (для обычного пользователя)
# ─────────────────────────────────────────────────────────────────────────
@router.post("/promo/activate", response_model=PromoActivateResponse)
async def activate(
    body: PromoActivateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        added, balance = await activate_promo(db, user, body.code)
    except PromoError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PromoActivateResponse(
        success=True,
        bonus_credits_added=added,
        new_balance=balance,
        message=f"+{added} bonus credits",
    )


# ─────────────────────────────────────────────────────────────────────────
# Создание промокода (только admin)
# ─────────────────────────────────────────────────────────────────────────
@router.post("/admin/promo", status_code=201, dependencies=[Depends(require_admin)])
async def create_promo(body: PromoCreateRequest, db: AsyncSession = Depends(get_db)):
    code_norm = body.code.strip().upper()
    res = await db.execute(select(PromoCode).where(PromoCode.code == code_norm))
    if res.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="code_already_exists")

    promo = PromoCode(
        code=code_norm,
        promo_type=PromoType.FIXED,
        bonus_credits=body.bonus_credits,
        max_activations=body.max_activations,
        valid_until=body.valid_until,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return {"id": promo.id, "code": promo.code, "bonus_credits": promo.bonus_credits}


@router.get("/admin/promo", dependencies=[Depends(require_admin)])
async def list_promos(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
    promos = res.scalars().all()
    return [
        {
            "id": p.id, "code": p.code, "bonus_credits": p.bonus_credits,
            "activations_count": p.activations_count,
            "max_activations": p.max_activations,
            "valid_until": p.valid_until, "is_active": p.is_active,
        }
        for p in promos
    ]


# ─────────────────────────────────────────────────────────────────────────
# Пополнение баланса (заглушка вместо платёжки)
# ─────────────────────────────────────────────────────────────────────────
@router.post("/billing/topup")
async def topup(
    body: TopUpRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Эмулирует успешный платёж и зачисляет credits на основной баланс."""
    await billing.add_paid(db, user, body.amount, reason="topup")
    await db.commit()
    return {
        "paid_credits": user.paid_credits,
        "bonus_credits": user.bonus_credits,
        "added": body.amount,
    }


# ─────────────────────────────────────────────────────────────────────────
# Простые stats (нужны для дашборда)
# ─────────────────────────────────────────────────────────────────────────
@router.get("/stats/me", response_model=StatsResponse)
async def my_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(func.count()).select_from(PredictionTask).where(PredictionTask.user_id == user.id)

    total = (await db.execute(base)).scalar_one()
    pending = (await db.execute(base.where(PredictionTask.status == TaskStatus.PENDING))).scalar_one()
    completed = (await db.execute(base.where(PredictionTask.status == TaskStatus.COMPLETED))).scalar_one()
    failed = (await db.execute(base.where(PredictionTask.status == TaskStatus.FAILED))).scalar_one()

    spent_q = (
        select(func.coalesce(func.sum(-(CreditTransaction.paid_delta + CreditTransaction.bonus_delta)), 0))
        .where(CreditTransaction.user_id == user.id, CreditTransaction.reason == "reserve")
    )
    spent = (await db.execute(spent_q)).scalar_one()

    return StatsResponse(
        total_predictions=total,
        total_credits_spent=int(spent),
        pending=pending,
        completed=completed,
        failed=failed,
    )
