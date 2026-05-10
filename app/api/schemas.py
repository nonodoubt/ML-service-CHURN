"""Pydantic-схемы для запросов и ответов API."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.db.models import TaskStatus


# ── Auth ─────────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMe(BaseModel):
    user_id: UUID
    email: str
    role: str
    tariff: str
    paid_credits: int
    bonus_credits: int
    total_credits: int


# ── Churn predict ────────────────────────────────────────────────────────
# Поля и допустимые значения соответствуют датасету churn.
class ChurnFeatures(BaseModel):
    ClientPeriod: int = Field(..., ge=0, le=200, description="Сколько месяцев клиент с нами")
    MonthlySpending: float = Field(..., ge=0)
    TotalSpent: float | str = Field(..., description="Float или ' ' (новый клиент)")
    Sex: Literal["Male", "Female"]
    IsSeniorCitizen: Literal[0, 1]
    HasPartner: Literal["Yes", "No"]
    HasChild: Literal["Yes", "No"]
    HasPhoneService: Literal["Yes", "No"]
    HasMultiplePhoneNumbers: Literal["Yes", "No", "No phone service"]
    HasInternetService: Literal["DSL", "Fiber optic", "No"]
    HasOnlineSecurityService: Literal["Yes", "No", "No internet service"]
    HasOnlineBackup: Literal["Yes", "No", "No internet service"]
    HasDeviceProtection: Literal["Yes", "No", "No internet service"]
    HasTechSupportAccess: Literal["Yes", "No", "No internet service"]
    HasOnlineTV: Literal["Yes", "No", "No internet service"]
    HasMovieSubscription: Literal["Yes", "No", "No internet service"]
    HasContractPhone: Literal["Month-to-month", "One year", "Two year"]
    IsBillingPaperless: Literal["Yes", "No"]
    PaymentMethod: Literal[
        "Electronic check", "Mailed check",
        "Bank transfer (automatic)", "Credit card (automatic)"
    ]

    model_config = {
        "json_schema_extra": {
            "example": {
                "ClientPeriod": 55,
                "MonthlySpending": 19.50,
                "TotalSpent": 1026.35,
                "Sex": "Male",
                "IsSeniorCitizen": 0,
                "HasPartner": "Yes",
                "HasChild": "Yes",
                "HasPhoneService": "Yes",
                "HasMultiplePhoneNumbers": "No",
                "HasInternetService": "No",
                "HasOnlineSecurityService": "No internet service",
                "HasOnlineBackup": "No internet service",
                "HasDeviceProtection": "No internet service",
                "HasTechSupportAccess": "No internet service",
                "HasOnlineTV": "No internet service",
                "HasMovieSubscription": "No internet service",
                "HasContractPhone": "One year",
                "IsBillingPaperless": "No",
                "PaymentMethod": "Mailed check",
            }
        }
    }


class PredictResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    message: str = "submitted"


class TaskResultResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    credits_charged: int = 0


class BatchPredictRequest(BaseModel):
    items: list[ChurnFeatures] = Field(..., min_length=1, max_length=10000)


# ── Promo ────────────────────────────────────────────────────────────────
class PromoActivateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class PromoActivateResponse(BaseModel):
    success: bool
    bonus_credits_added: int
    new_balance: int
    message: str


class PromoCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    bonus_credits: int = Field(..., ge=1)
    max_activations: Optional[int] = Field(None, ge=1)
    valid_until: Optional[datetime] = None


# ── Health ───────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    model: str


# ── Admin ────────────────────────────────────────────────────────────────
class TopUpRequest(BaseModel):
    amount: int = Field(..., ge=1)


class StatsResponse(BaseModel):
    total_predictions: int
    total_credits_spent: int
    pending: int
    completed: int
    failed: int
