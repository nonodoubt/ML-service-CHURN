"""Загрузка обученной модели и обёртка для инференса.

Внутри joblib-файла лежит весь Pipeline (включая FunctionTransformer
с feature_engineering). Поэтому нам не нужно дублировать тут логику
препроцессинга — просто передаём pandas.DataFrame в model.predict.
"""

import logging
from pathlib import Path
from typing import Optional

import joblib
import pandas as pd

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Поля ровно в том же порядке, что в датасете (важно для DataFrame)
FEATURE_COLUMNS = [
    'ClientPeriod', 'MonthlySpending', 'TotalSpent',
    'Sex', 'IsSeniorCitizen', 'HasPartner', 'HasChild',
    'HasPhoneService', 'HasMultiplePhoneNumbers', 'HasInternetService',
    'HasOnlineSecurityService', 'HasOnlineBackup', 'HasDeviceProtection',
    'HasTechSupportAccess', 'HasOnlineTV', 'HasMovieSubscription',
    'HasContractPhone', 'IsBillingPaperless', 'PaymentMethod',
]

_model = None


def load_model() -> None:
    """Грузим модель один раз при старте."""
    global _model
    path = Path(settings.model_path)
    if not path.exists():
        logger.warning("Model file %s not found — using stub", path)
        _model = _StubModel()
        return
    _model = joblib.load(path)
    logger.info("Model loaded from %s", path)


def get_model():
    if _model is None:
        load_model()
    return _model


def predict_one(features: dict) -> dict:
    """Принимает dict с 19 полями, возвращает {'churn': 0|1, 'probability': float}."""
    model = get_model()
    df = pd.DataFrame([features], columns=FEATURE_COLUMNS)
    proba = float(model.predict_proba(df)[0, 1])
    label = int(proba >= 0.5)
    # В ТЗ: 1 = надёжный, 0 = нет. У нас target Churn=1 значит "уйдёт", т.е. ненадёжный.
    # Поэтому reliable = 1 - churn_label.
    reliable = 1 - label
    return {
        "churn": label,
        "reliable": reliable,
        "probability_churn": round(proba, 4),
    }


class _StubModel:
    """Заглушка, чтобы сервис стартовал без обученной модели."""

    def predict_proba(self, X):
        import numpy as np
        n = len(X)
        p = np.full((n, 2), 0.5)
        return p
