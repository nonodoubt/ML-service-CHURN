"""Обучение модели при первом запуске.

Запускается автоматически из docker-compose как init-контейнер.
Если models/churn_model.joblib уже есть — ничего не делает.
Если нет — обучает pipeline на data/train.csv и сохраняет.
"""

import sys
import os

# Корень проекта — чтобы импорт app.ml.preprocessing работал
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

OUTPUT = Path("models/churn_model.joblib")
TRAIN_CSV = Path("data/train.csv")


def main():
    # Если модель уже обучена — пропускаем
    if OUTPUT.exists():
        print(f"[train] Model already exists at {OUTPUT}, skipping training.")
        return

    if not TRAIN_CSV.exists():
        print(f"[train] WARNING: {TRAIN_CSV} not found. Service will start with stub model.")
        print(f"[train] Put your train.csv into data/ folder and rebuild.")
        return

    print(f"[train] Training model from {TRAIN_CSV}...")

    import joblib
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler, OneHotEncoder, FunctionTransformer
    from sklearn.linear_model import SGDClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score

    from app.ml.preprocessing import feature_engineering, NUM_COLS, CAT_COLS

    RAW_FEATURES = [
        'ClientPeriod', 'MonthlySpending', 'TotalSpent',
        'Sex', 'IsSeniorCitizen', 'HasPartner', 'HasChild',
        'HasPhoneService', 'HasMultiplePhoneNumbers', 'HasInternetService',
        'HasOnlineSecurityService', 'HasOnlineBackup', 'HasDeviceProtection',
        'HasTechSupportAccess', 'HasOnlineTV', 'HasMovieSubscription',
        'HasContractPhone', 'IsBillingPaperless', 'PaymentMethod',
    ]

    df = pd.read_csv(TRAIN_CSV)
    X = df[RAW_FEATURES].copy()
    y = df['Churn']

    preprocessor = ColumnTransformer(transformers=[
        ('num', StandardScaler(), NUM_COLS),
        ('cat', OneHotEncoder(handle_unknown='ignore'), CAT_COLS),
    ])

    pipeline = Pipeline(steps=[
        ('fe',   FunctionTransformer(feature_engineering, validate=False)),
        ('prep', preprocessor),
        ('clf',  SGDClassifier(loss='log_loss', alpha=0.0001, max_iter=1000, random_state=42)),
    ])

    X_train, X_valid, y_train, y_valid = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    pipeline.fit(X_train, y_train)

    val_proba = pipeline.predict_proba(X_valid)[:, 1]
    roc = roc_auc_score(y_valid, val_proba)
    print(f"[train] Validation ROC-AUC: {roc:.4f}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, OUTPUT)
    print(f"[train] Saved model -> {OUTPUT}")


if __name__ == "__main__":
    main()
