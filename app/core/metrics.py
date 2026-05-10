"""Бизнес-метрики для Grafana.

Стандартные метрики (latency, status_code, и т.п.) даёт
prometheus-fastapi-instrumentator. Тут — наши кастомные.
"""

from prometheus_client import Counter, Gauge, Histogram

predictions_submitted_total = Counter(
    "ml_predictions_submitted_total",
    "Сколько прогнозов отправлено в очередь",
    ["endpoint"],
)

predictions_completed_total = Counter(
    "ml_predictions_completed_total",
    "Сколько прогнозов успешно завершилось",
)

predictions_failed_total = Counter(
    "ml_predictions_failed_total",
    "Сколько прогнозов упало с ошибкой",
)

credits_spent_total = Counter(
    "ml_credits_spent_total",
    "Сколько кредитов потрачено суммарно",
    ["kind"],   # paid|bonus
)

rate_limit_blocks_total = Counter(
    "ml_rate_limit_blocks_total",
    "Сколько раз срабатывал rate-limit",
    ["reason"],   # rate|concurrent|credits
)

active_predictions = Gauge(
    "ml_active_predictions",
    "Текущее число активных предсказаний",
)

prediction_duration_seconds = Histogram(
    "ml_prediction_duration_seconds",
    "Время выполнения предсказания, секунды",
)
