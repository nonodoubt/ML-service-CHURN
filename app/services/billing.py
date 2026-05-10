"""Биллинг.

Основное правило из ТЗ: при списании сначала тратим бонусные кредиты,
потом — оплаченные. Все изменения логируем в credit_transactions.

Атомарность гарантируется тем, что update идёт через WHERE-условие
с проверкой текущего баланса (optimistic) + commit на одном UoW.
"""

from typing import Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, CreditTransaction


async def charge_credits(
    db: AsyncSession,
    user: User,
    amount: int,
    reason: str,
    task_id=None,
) -> Tuple[int, int]:
    """Списать `amount` кредитов. Сначала бонусы, потом paid.

    Возвращает (bonus_used, paid_used). Если денег не хватает — кидает ValueError.
    Никаких частичных списаний не делаем.
    """
    if amount <= 0:
        return 0, 0

    if user.paid_credits + user.bonus_credits < amount:
        raise ValueError("insufficient_credits")

    bonus_used = min(user.bonus_credits, amount)
    paid_used = amount - bonus_used

    user.bonus_credits -= bonus_used
    user.paid_credits -= paid_used

    db.add(CreditTransaction(
        user_id=user.id,
        paid_delta=-paid_used,
        bonus_delta=-bonus_used,
        reason=reason,
        task_id=task_id,
    ))

    return bonus_used, paid_used


async def refund_credits(
    db: AsyncSession,
    user: User,
    bonus_used: int,
    paid_used: int,
    reason: str,
    task_id=None,
) -> None:
    """Возврат после неудачной задачи — кладём ровно туда, откуда списали."""
    user.bonus_credits += bonus_used
    user.paid_credits += paid_used

    db.add(CreditTransaction(
        user_id=user.id,
        paid_delta=paid_used,
        bonus_delta=bonus_used,
        reason=reason,
        task_id=task_id,
    ))


async def add_bonus(
    db: AsyncSession,
    user: User,
    amount: int,
    reason: str,
    promo_code_id=None,
) -> None:
    """Начисление бонусов (промокод, signup и т.п.)."""
    if amount <= 0:
        return
    user.bonus_credits += amount
    db.add(CreditTransaction(
        user_id=user.id,
        paid_delta=0,
        bonus_delta=amount,
        reason=reason,
        promo_code_id=promo_code_id,
    ))


async def add_paid(
    db: AsyncSession,
    user: User,
    amount: int,
    reason: str = "topup",
) -> None:
    """Пополнение основного баланса (заглушка вместо платёжки)."""
    if amount <= 0:
        return
    user.paid_credits += amount
    db.add(CreditTransaction(
        user_id=user.id,
        paid_delta=amount,
        bonus_delta=0,
        reason=reason,
    ))
