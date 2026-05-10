"""Celery-воркер.

После всех проверок и резерва кредитов API кидает сюда задачу.
Воркер крутит prediction в синхронном режиме (это CPU-bound),
обновляет статус в БД и освобождает concurrent-слот.
"""

import logging
from datetime import datetime, timezone, timedelta

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


celery_app = Celery(
    "ml_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                 # если воркер упадёт — сообщение вернётся в очередь
    worker_prefetch_multiplier=1,
    result_expires=3600,
    beat_schedule={
        "cleanup-stale-tasks": {
            "task": "app.tasks.worker.cleanup_stale_tasks",
            "schedule": 300.0,
        },
    },
)


# Синхронный engine — Celery работает в обычных процессах
_engine = None
_Session = None


def _session() -> Session:
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url_sync, pool_size=5, pool_pre_ping=True)
        _Session = sessionmaker(bind=_engine)
    return _Session()


def _release_slot(user_id: str):
    import redis
    r = redis.from_url(settings.redis_url, decode_responses=True)
    key = f"conc:{user_id}"
    val = r.decr(key)
    if val <= 0:
        r.delete(key)
    r.close()


def _refund(session, task, user_id):
    """Откатить резерв кредитов при ошибке. Бонусы возвращаем как бонусы,
    paid — как paid (информация лежит в credit_transactions)."""
    from app.db.models import User, CreditTransaction
    user = session.query(User).filter_by(id=user_id).first()
    if not user or task.credits_charged <= 0:
        return

    # Берём последнюю транзакцию резерва, чтобы понять, что было списано откуда
    tx = (session.query(CreditTransaction)
            .filter_by(task_id=task.id, reason="reserve")
            .order_by(CreditTransaction.id.desc())
            .first())
    if tx is None:
        # на всякий случай — возвращаем всё как paid
        user.paid_credits += task.credits_charged
    else:
        user.bonus_credits += abs(tx.bonus_delta)
        user.paid_credits += abs(tx.paid_delta)

    session.add(CreditTransaction(
        user_id=user_id,
        paid_delta=abs(tx.paid_delta) if tx else task.credits_charged,
        bonus_delta=abs(tx.bonus_delta) if tx else 0,
        reason="refund",
        task_id=task.id,
    ))


@celery_app.task(
    bind=True,
    name="app.tasks.worker.run_prediction",
    max_retries=2,
    default_retry_delay=10,
)
def run_prediction(self, task_id: str, user_id: str, features: dict):
    """Один churn-предикт."""
    from app.db.models import PredictionTask, TaskStatus
    from app.ml.model import predict_one

    s = _session()
    try:
        task = s.query(PredictionTask).filter_by(id=task_id).first()
        if not task:
            logger.error("Task %s not found", task_id)
            return {"error": "task_not_found"}

        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now(timezone.utc)
        s.commit()

        result = predict_one(features)

        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.now(timezone.utc)
        s.commit()
        return {"task_id": task_id, **result}

    except Exception as exc:
        s.rollback()
        try:
            task = s.query(PredictionTask).filter_by(id=task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error = str(exc)[:500]
                task.completed_at = datetime.now(timezone.utc)
                _refund(s, task, user_id)
                s.commit()
        except Exception:
            s.rollback()
            logger.exception("Failed to mark task as failed")
        raise self.retry(exc=exc)

    finally:
        _release_slot(user_id)
        s.close()


@celery_app.task(
    bind=True,
    name="app.tasks.worker.run_batch_prediction",
    max_retries=1,
)
def run_batch_prediction(self, task_id: str, user_id: str, items: list):
    """Пачкой — для батч-эндпоинта."""
    from app.db.models import PredictionTask, TaskStatus
    from app.ml.model import predict_one

    s = _session()
    try:
        task = s.query(PredictionTask).filter_by(id=task_id).first()
        if not task:
            return {"error": "task_not_found"}

        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.now(timezone.utc)
        s.commit()

        results = [predict_one(item) for item in items]

        task.status = TaskStatus.COMPLETED
        task.result = {"predictions": results, "count": len(results)}
        task.completed_at = datetime.now(timezone.utc)
        s.commit()
        return {"task_id": task_id, "count": len(results)}

    except Exception as exc:
        s.rollback()
        try:
            task = s.query(PredictionTask).filter_by(id=task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error = str(exc)[:500]
                task.completed_at = datetime.now(timezone.utc)
                _refund(s, task, user_id)
                s.commit()
        except Exception:
            s.rollback()
        raise self.retry(exc=exc)

    finally:
        _release_slot(user_id)
        s.close()


@celery_app.task(name="app.tasks.worker.cleanup_stale_tasks")
def cleanup_stale_tasks():
    """Отсекаем зависшие PROCESSING-задачи (если воркер упал в процессе)."""
    from app.db.models import PredictionTask, TaskStatus
    s = _session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        stale = (s.query(PredictionTask)
                  .filter(PredictionTask.status == TaskStatus.PROCESSING,
                          PredictionTask.started_at < cutoff)
                  .all())
        for t in stale:
            t.status = TaskStatus.FAILED
            t.error = "timeout"
            t.completed_at = datetime.now(timezone.utc)
            _release_slot(str(t.user_id))
        s.commit()
        if stale:
            logger.info("Cleaned up %d stale tasks", len(stale))
    except Exception:
        s.rollback()
    finally:
        s.close()
