"""Эндпоинты предсказания churn'а.

Поток ровно по схеме:
  POST /ml/submit -> проверки (credits/concurrent/rate) -> резерв -> Celery
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas import (
    ChurnFeatures, BatchPredictRequest,
    PredictResponse, TaskResultResponse, HealthResponse,
)
from app.core import metrics
from app.core.limiter import (
    check_rate_limit, acquire_concurrent_slot, release_concurrent_slot, get_redis,
)
from app.db.models import User, PredictionTask, TaskStatus
from app.db.session import get_db
from app.db import session as db_session
from app.ml.model import get_model
from app.services import billing

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ml"])


# ─────────────────────────────────────────────────────────────────────────
# SYNC: health
# ─────────────────────────────────────────────────────────────────────────
@router.get("/health", response_model=HealthResponse)
async def health():
    """Простая синхронная проверка — БД, Redis, модель."""
    db_status = redis_status = model_status = "ok"

    try:
        async with db_session.engine.connect() as conn:
            await conn.execute(select(func.now()))
    except Exception as e:
        db_status = f"error: {e}"

    try:
        r = await get_redis()
        await r.ping()
    except Exception as e:
        redis_status = f"error: {e}"

    try:
        get_model()
    except Exception as e:
        model_status = f"error: {e}"

    overall = "ok" if all(s == "ok" for s in (db_status, redis_status, model_status)) else "degraded"
    return HealthResponse(status=overall, db=db_status, redis=redis_status, model=model_status)


# ─────────────────────────────────────────────────────────────────────────
# Общая логика проверок (используется и для submit, и для batch)
# ─────────────────────────────────────────────────────────────────────────
async def _run_checks_and_charge(
    db: AsyncSession, user: User, cost: int,
):
    """Прогоняем все 4 двери из схемы. Если всё ок — списываем cost кредитов."""
    tariff = user.tariff

    # 1) Кредитов достаточно?
    if user.paid_credits + user.bonus_credits < cost:
        metrics.rate_limit_blocks_total.labels(reason="credits").inc()
        raise HTTPException(status_code=402, detail={
            "error": "insufficient_credits",
            "required": cost,
            "available": user.paid_credits + user.bonus_credits,
        })

    # 2) Лимит concurrent
    ok = await acquire_concurrent_slot(str(user.id), tariff.max_concurrent)
    if not ok:
        metrics.rate_limit_blocks_total.labels(reason="concurrent").inc()
        raise HTTPException(status_code=429, detail={
            "error": "concurrent_limit_exceeded",
            "max_concurrent": tariff.max_concurrent,
        })

    # 3) Rate limit
    allowed = await check_rate_limit(str(user.id), tariff.rate_limit, tariff.rate_window)
    if not allowed:
        await release_concurrent_slot(str(user.id))
        metrics.rate_limit_blocks_total.labels(reason="rate").inc()
        raise HTTPException(status_code=429, detail={
            "error": "rate_limit_exceeded",
            "limit": tariff.rate_limit,
            "window_seconds": tariff.rate_window,
        })

    # 4) Резерв кредитов (бонусы первыми, потом paid)
    try:
        bonus_used, paid_used = await billing.charge_credits(
            db, user, cost, reason="reserve",
        )
    except ValueError:
        # маловероятно (мы уже проверили выше), но на всякий случай освобождаем слот
        await release_concurrent_slot(str(user.id))
        raise HTTPException(status_code=402, detail={"error": "insufficient_credits"})

    metrics.credits_spent_total.labels(kind="bonus").inc(bonus_used)
    metrics.credits_spent_total.labels(kind="paid").inc(paid_used)


# ─────────────────────────────────────────────────────────────────────────
# ASYNC: одиночный churn-предикт
# ─────────────────────────────────────────────────────────────────────────
@router.post("/ml/submit", response_model=PredictResponse, status_code=202)
async def submit_prediction(
    body: ChurnFeatures,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cost = user.tariff.cost_per_prediction
    await _run_checks_and_charge(db, user, cost)

    task = PredictionTask(
        user_id=user.id,
        input_data=body.model_dump(),
        status=TaskStatus.PENDING,
        credits_charged=cost,
    )
    db.add(task)
    # Привязываем последнюю транзакцию-резерв к задаче
    await db.flush()

    from app.db.models import CreditTransaction
    res = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user.id, CreditTransaction.reason == "reserve")
        .order_by(CreditTransaction.id.desc())
        .limit(1)
    )
    last_tx = res.scalar_one_or_none()
    if last_tx and last_tx.task_id is None:
        last_tx.task_id = task.id

    await db.commit()
    await db.refresh(task)

    # Отправляем в Celery
    from app.tasks.worker import run_prediction
    celery_res = run_prediction.delay(
        task_id=str(task.id),
        user_id=str(user.id),
        features=body.model_dump(),
    )
    task.celery_task_id = celery_res.id
    await db.commit()

    metrics.predictions_submitted_total.labels(endpoint="submit").inc()

    return PredictResponse(
        task_id=task.id, status=TaskStatus.PENDING,
        message=f"Submitted. Cost: {cost} credits.",
    )


# ─────────────────────────────────────────────────────────────────────────
# Batch (Celery)
# ─────────────────────────────────────────────────────────────────────────
@router.post("/ml/batch", response_model=PredictResponse, status_code=202)
async def submit_batch(
    body: BatchPredictRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cost = user.tariff.cost_per_prediction * len(body.items)
    await _run_checks_and_charge(db, user, cost)

    items = [it.model_dump() for it in body.items]

    task = PredictionTask(
        user_id=user.id,
        input_data={"items": items, "batch_size": len(items)},
        status=TaskStatus.PENDING,
        credits_charged=cost,
    )
    db.add(task)
    await db.flush()

    from app.db.models import CreditTransaction
    res = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user.id, CreditTransaction.reason == "reserve")
        .order_by(CreditTransaction.id.desc())
        .limit(1)
    )
    last_tx = res.scalar_one_or_none()
    if last_tx and last_tx.task_id is None:
        last_tx.task_id = task.id

    await db.commit()
    await db.refresh(task)

    from app.tasks.worker import run_batch_prediction
    celery_res = run_batch_prediction.delay(
        task_id=str(task.id),
        user_id=str(user.id),
        items=items,
    )
    task.celery_task_id = celery_res.id
    await db.commit()

    metrics.predictions_submitted_total.labels(endpoint="batch").inc()

    return PredictResponse(
        task_id=task.id, status=TaskStatus.PENDING,
        message=f"Batch of {len(items)} submitted. Cost: {cost} credits.",
    )


# ─────────────────────────────────────────────────────────────────────────
# Получить статус задачи
# ─────────────────────────────────────────────────────────────────────────
@router.get("/ml/tasks/{task_id}", response_model=TaskResultResponse)
async def get_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(PredictionTask).where(
            PredictionTask.id == task_id,
            PredictionTask.user_id == user.id,
        )
    )
    task = res.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    return TaskResultResponse(
        task_id=task.id,
        status=task.status,
        result=task.result,
        error=task.error,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        credits_charged=task.credits_charged,
    )


@router.get("/ml/tasks", response_model=list[TaskResultResponse])
async def list_tasks(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """История задач пользователя — нужно для дашборда."""
    limit = min(max(limit, 1), 100)
    res = await db.execute(
        select(PredictionTask)
        .where(PredictionTask.user_id == user.id)
        .order_by(PredictionTask.created_at.desc())
        .limit(limit)
    )
    tasks = res.scalars().all()
    return [
        TaskResultResponse(
            task_id=t.id, status=t.status, result=t.result, error=t.error,
            created_at=t.created_at, started_at=t.started_at,
            completed_at=t.completed_at, credits_charged=t.credits_charged,
        )
        for t in tasks
    ]
