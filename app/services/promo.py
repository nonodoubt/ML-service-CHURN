"""Активация промокодов.

Проверки:
  - код существует и активен
  - срок действия не истёк
  - не превышено max_activations
  - тот же юзер не активировал его раньше (UniqueConstraint в БД)
"""

from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PromoCode, PromoActivation, User
from app.services import billing


class PromoError(Exception):
    pass


async def activate_promo(db: AsyncSession, user: User, code: str) -> Tuple[int, int]:
    """Активирует промокод. Возвращает (added, new_total_balance)."""
    # Достаём промокод по нормализованному code
    code_norm = code.strip().upper()
    res = await db.execute(select(PromoCode).where(PromoCode.code == code_norm))
    promo = res.scalar_one_or_none()
    if promo is None or not promo.is_active:
        raise PromoError("promo_not_found")

    # Срок действия. SQLite хранит datetime без tz, поэтому нормализуем.
    if promo.valid_until is not None:
        valid_until = promo.valid_until
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if valid_until < datetime.now(timezone.utc):
            raise PromoError("promo_expired")

    # Лимит активаций
    if promo.max_activations is not None and promo.activations_count >= promo.max_activations:
        raise PromoError("promo_exhausted")

    # Запись активации с unique-ограничением — это и есть наша защита
    # от повторного использования одним юзером
    activation = PromoActivation(user_id=user.id, promo_code_id=promo.id)
    db.add(activation)

    promo.activations_count += 1
    await billing.add_bonus(db, user, promo.bonus_credits, reason="promo", promo_code_id=promo.id)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise PromoError("already_activated")

    return promo.bonus_credits, user.paid_credits + user.bonus_credits
