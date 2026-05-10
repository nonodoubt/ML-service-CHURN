"""Модели БД.

Балансы храним в виде двух колонок: paid_credits и bonus_credits.
При списании сначала тратим бонусные — это требование из ТЗ.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Enum, ForeignKey, Text, JSON,
    Boolean, UniqueConstraint, Index, CheckConstraint, Uuid,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base

# Универсальный UUID-тип. На postgres ляжет в native uuid,
# на sqlite — в CHAR(32). as_uuid=True значит, что в питоне это всегда uuid.UUID.
UUID = Uuid(as_uuid=True)


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class TariffTier(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class PromoType(str, enum.Enum):
    FIXED = "fixed"        # даёт фиксированное количество кредитов
    PERCENT = "percent"    # процентная скидка на следующее пополнение (тут не используем,
                            # но оставлено как расширение)


# ─────────────────────────────────────────────────────────────────────────
# Тарифы
# ─────────────────────────────────────────────────────────────────────────
class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tier = Column(Enum(TariffTier), unique=True, nullable=False)
    rate_limit = Column(Integer, nullable=False, default=60)        # запросов
    rate_window = Column(Integer, nullable=False, default=60)        # секунд
    max_concurrent = Column(Integer, nullable=False, default=5)
    cost_per_prediction = Column(Integer, nullable=False, default=1)


# ─────────────────────────────────────────────────────────────────────────
# Пользователи
# ─────────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.USER)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=False)

    # Два кошелька. Списываем сначала bonus, потом paid.
    paid_credits = Column(Integer, nullable=False, default=0)
    bonus_credits = Column(Integer, nullable=False, default=0)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tariff = relationship("Tariff", lazy="joined")

    __table_args__ = (
        CheckConstraint("paid_credits >= 0", name="paid_credits_nonneg"),
        CheckConstraint("bonus_credits >= 0", name="bonus_credits_nonneg"),
    )

    @property
    def total_credits(self) -> int:
        return self.paid_credits + self.bonus_credits


# ─────────────────────────────────────────────────────────────────────────
# Промокоды
# ─────────────────────────────────────────────────────────────────────────
class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    promo_type = Column(Enum(PromoType), nullable=False, default=PromoType.FIXED)
    bonus_credits = Column(Integer, nullable=False, default=0)
    max_activations = Column(Integer, nullable=True)   # None = безлимит
    activations_count = Column(Integer, nullable=False, default=0)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PromoActivation(Base):
    """Лог активаций — нужен, чтобы один и тот же юзер не активировал код дважды."""
    __tablename__ = "promo_activations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    activated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "promo_code_id", name="uq_user_promo"),
    )


# ─────────────────────────────────────────────────────────────────────────
# Задачи и транзакции
# ─────────────────────────────────────────────────────────────────────────
class PredictionTask(Base):
    __tablename__ = "prediction_tasks"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    input_data = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)            # {"churn": 0/1, "probability": 0..1}
    error = Column(Text, nullable=True)
    credits_charged = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    celery_task_id = Column(String(255), nullable=True, index=True)

    __table_args__ = (
        Index("ix_task_user_status", "user_id", "status"),
    )


class CreditTransaction(Base):
    """Аудит-лог всех движений кредитов."""
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    paid_delta = Column(Integer, nullable=False, default=0)    # изменение paid-баланса
    bonus_delta = Column(Integer, nullable=False, default=0)   # изменение bonus-баланса
    reason = Column(String(64), nullable=False)
    task_id = Column(UUID, ForeignKey("prediction_tasks.id"), nullable=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
