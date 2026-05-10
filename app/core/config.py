from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # БД
    database_url: str = "postgresql+asyncpg://mluser:mlpass@localhost:5432/mlservice"
    database_url_sync: str = "postgresql+psycopg2://mluser:mlpass@localhost:5432/mlservice"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # JWT
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Модель
    model_path: str = "models/churn_model.joblib"

    # Лимиты по умолчанию
    default_rate_limit: int = 60
    default_rate_window: int = 60
    default_max_concurrent: int = 5
    prediction_cost: int = 1
    signup_bonus_credits: int = 20

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
