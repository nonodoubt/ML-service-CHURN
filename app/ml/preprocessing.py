"""Препроцессинг признаков клиента.

ВАЖНО: эта функция должна быть в одном и том же модульном пути и при обучении,
и при инференсе — иначе joblib не сможет загрузить pickled-pipeline.
Поэтому она живёт здесь, в app/ml/preprocessing.py, а notebook импортирует её
отсюда же (см. scripts/notebook_cell.py).
"""

import pandas as pd


INTERNET_SERVICES = [
    'HasOnlineSecurityService', 'HasOnlineBackup', 'HasDeviceProtection',
    'HasTechSupportAccess', 'HasOnlineTV', 'HasMovieSubscription',
]


def feature_engineering(X: pd.DataFrame) -> pd.DataFrame:
    """Препроцессинг сырых клиентских данных, как в EDA из churn.ipynb.

    Действия:
      - TotalSpent: пробелы → 0, кастуем во float
      - num_internet_services: счётчик 'Yes' среди 6 интернет-фичей
      - дропаем 6 интернет-фичей и HasMultiplePhoneNumbers
    """
    X = X.copy()

    X.loc[X['TotalSpent'].astype(str).str.strip() == '', 'TotalSpent'] = 0
    X['TotalSpent'] = X['TotalSpent'].astype(float)

    X['num_internet_services'] = X[INTERNET_SERVICES].apply(
        lambda row: (row == 'Yes').sum(), axis=1
    )

    X = X.drop(columns=INTERNET_SERVICES + ['HasMultiplePhoneNumbers'])
    return X


# Колонки после feature_engineering
NUM_COLS = ['ClientPeriod', 'MonthlySpending', 'TotalSpent', 'num_internet_services']
CAT_COLS = [
    'Sex', 'IsSeniorCitizen', 'HasPartner', 'HasChild',
    'HasPhoneService', 'HasInternetService',
    'HasContractPhone', 'IsBillingPaperless', 'PaymentMethod',
]
