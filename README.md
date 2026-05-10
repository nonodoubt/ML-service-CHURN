# 🔮 Churn Prediction Service

> ML-сервис предсказания оттока клиентов с биллингом, JWT-аутентификацией, асинхронной очередью задач и мониторингом.

Модель: **SGDClassifier** (scikit-learn) · Биллинг: **кредитная система с промокодами** · Очередь: **Celery + Redis** · БД: **PostgreSQL**

---

## Интерфейс

| Панель пользователя | Предсказание | Админ-панель | Мониторинг |
|---|---|---|---|
| ![view](images/view.png) | ![score](images/score.png) | ![admin](images/admin.png) | ![grafana](images/grafana.png) |

---

## 🚀Быстрый старт

```bash
docker compose up -d --build
```

При сборке образа автоматически:
- 🤖 модель обучается на `data/train.csv`
- 👤 создаётся администратор и промокод `WELCOME50`
- 🗄 инициализируется БД с тарифами

---

## Интерфейсы

| URL | Назначение | Доступ |
|-----|-----------|--------|
| [localhost:8501](http://localhost:8501) | **Streamlit** — веб-интерфейс | регистрация или `admin@gmail.com` / `admin12345` |
| [localhost:8000/docs](http://localhost:8000/docs) | **Swagger** — документация API | без авторизации |
| [localhost:3000](http://localhost:3000) | **Grafana** — дашборды метрик | `admin` / `admin` |
| [localhost:9090](http://localhost:9090) | **Prometheus** — сырые метрики | без авторизации |

---

## Входные данные модели

| Поле | Описание | Значения |
|------|----------|----------|
| `ClientPeriod` | Сколько месяцев клиент с нами | `0..72` |
| `MonthlySpending` | Ежемесячные траты | `float` |
| `TotalSpent` | Всего потрачено | `float` |
| `Sex` | Пол | `Male / Female` |
| `IsSeniorCitizen` | Пенсионер | `0 / 1` |
| `HasPartner` | Есть партнёр | `Yes / No` |
| `HasChild` | Есть ребёнок | `Yes / No` |
| `HasPhoneService` | Телефония | `Yes / No` |
| `HasMultiplePhoneNumbers` | Несколько номеров | `Yes / No / No phone service` |
| `HasInternetService` | Тип интернета | `DSL / Fiber optic / No` |
| `HasOnlineSecurityService` | Онлайн-безопасность | `Yes / No / No internet service` |
| `HasOnlineBackup` | Онлайн-бэкап | `Yes / No / No internet service` |
| `HasDeviceProtection` | Защита устройства | `Yes / No / No internet service` |
| `HasTechSupportAccess` | Техподдержка | `Yes / No / No internet service` |
| `HasOnlineTV` | ТВ | `Yes / No / No internet service` |
| `HasMovieSubscription` | Кино-подписка | `Yes / No / No internet service` |
| `HasContractPhone` | Тип контракта | `Month-to-month / One year / Two year` |
| `IsBillingPaperless` | Безбумажный биллинг | `Yes / No` |
| `PaymentMethod` | Способ оплаты | `Electronic check / Mailed check / Bank transfer / Credit card` |

---

## Биллинг

- Реализован **Вариант А** — система промокодов
- 1 предсказание = **1 кредит**
- При регистрации — тариф **Free** + **20 бонусных кредитов**
- Сначала списываются **бонусные** кредиты, потом платные
- Промокоды создаются и управляются через **Streamlit-админку**

| Тариф | Rate limit | Concurrent | Кредитов |
|-------|-----------|------------|---------|
| Free | 10 / мин | 1 | 50 |
| Basic | 60 / мин | 5 | 5 000 |
| Pro | 300 / мин | 20 | 50 000 |

---

## Архитектура

```
docker compose up --build
        │
        ▼
  entrypoint.sh
        ├── Создание таблиц БД
        ├── Seed: тарифы + админ + промокод WELCOME50
        └── uvicorn app.main:app

  + celery_worker   — асинхронные предсказания
  + celery_beat     — периодические задачи (очистка зависших)
  + streamlit       — веб-интерфейс
  + prometheus      — сбор метрик
  + grafana         — визуализация
```

---

## Структура проекта

```
├── app/
│   ├── api/            # auth, predictions, promo
│   ├── core/           # config, security, limiter, metrics
│   ├── db/             # модели БД, сессия
│   ├── ml/             # загрузка модели, preprocessing
│   ├── services/       # billing, promo logic
│   ├── tasks/          # Celery worker
│   └── main.py
├── data/
│   └── train.csv       # ← данные для обучения модели
├── models/             # обученная модель (создаётся при build)
├── streamlit_app/      # веб-интерфейс
├── monitoring/         # Prometheus + Grafana
├── scripts/            # train_model.py, seed.py
├── tests/              # 33 pytest-теста, покрытие 77%
├── docs/               # бизнес-план
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── .env.example        # шаблон переменных окружения
└── requirements.txt
```

---

## Переменные окружения

Все секреты хранятся в `.env`
. Шаблон: `.env.example`

| Переменная | Назначение |
|-----------|-----------|
| `POSTGRES_PASSWORD` | Пароль базы данных |
| `JWT_SECRET` | Секрет для подписи токенов |
| `ADMIN_EMAIL` | Email администратора |
| `ADMIN_PASSWORD` | Пароль администратора |
| `GF_SECURITY_ADMIN_PASSWORD` | Пароль Grafana |

---

## Тесты

```bash
docker compose exec app pytest
```

**33 теста · покрытие 77%**

Покрыты: аутентификация, биллинг (bonus-first), промокоды, предсказания, валидация входных данных, ML-модель.

---

## Бизнес-план

Бизнес-план с финмоделью → [docs/BUSINESS_PLAN.md](docs/BUSINESS_PLAN.md)