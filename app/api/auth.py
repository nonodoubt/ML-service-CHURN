"""Регистрация и логин."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas import (
    UserRegister, UserLogin, TokenResponse, UserMe,
)
from app.core.config import get_settings
from app.core.security import hash_password, verify_password, create_access_token
from app.db.models import User, Tariff, TariffTier, UserRole
from app.db.session import get_db
from app.services import billing

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    # Проверка дубликата
    res = await db.execute(select(User).where(User.email == body.email))
    if res.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="email_already_registered")

    # Берём бесплатный тариф по умолчанию
    res = await db.execute(select(Tariff).where(Tariff.tier == TariffTier.FREE))
    tariff = res.scalar_one_or_none()
    if tariff is None:
        raise HTTPException(status_code=500, detail="default_tariff_missing")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        tariff_id=tariff.id,
        role=UserRole.USER,
    )
    db.add(user)
    await db.flush()

    # Подарочные кредиты при регистрации
    if settings.signup_bonus_credits > 0:
        await billing.add_bonus(db, user, settings.signup_bonus_credits, reason="signup_bonus")

    await db.commit()
    await db.refresh(user)

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == body.email))
    user = res.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="user_disabled")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserMe)
async def me(user: User = Depends(get_current_user)):
    return UserMe(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        tariff=user.tariff.tier.value,
        paid_credits=user.paid_credits,
        bonus_credits=user.bonus_credits,
        total_credits=user.paid_credits + user.bonus_credits,
    )
