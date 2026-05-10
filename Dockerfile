FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Обучаем модель прямо при сборке образа — если train.csv и скрипт есть
RUN python scripts/train_model.py || echo "Model training skipped (no train.csv?)"
