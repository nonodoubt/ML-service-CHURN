"""Streamlit-фронт для Churn Prediction Service."""

import os
import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime

API = os.getenv("API_URL", "http://app:8000")

st.set_page_config(page_title="Churn Predictor", layout="centered")

if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def fetch_me():
    if not st.session_state.token:
        return None
    r = requests.get(f"{API}/auth/me", headers=auth_headers(), timeout=5)
    if r.status_code == 200:
        st.session_state.user = r.json()
        return st.session_state.user
    st.session_state.token = None
    return None


# ─────────────────────────────────────────────────────────────────────────
# Экран входа
# ─────────────────────────────────────────────────────────────────────────
def render_login():
    st.title("🔐 Churn Service")
    tab_login, tab_signup = st.tabs(["Вход", "Регистрация"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти"):
                r = requests.post(
                    f"{API}/auth/login",
                    json={"email": email, "password": password},
                    timeout=5,
                )
                if r.status_code == 200:
                    st.session_state.token = r.json()["access_token"]
                    fetch_me()
                    st.rerun()
                else:
                    st.error(f"Ошибка: {r.json().get('detail', r.text)}")

    with tab_signup:
        with st.form("signup_form"):
            email_s = st.text_input("Email", key="se")
            password_s = st.text_input("Пароль (мин. 6)", type="password", key="sp")
            if st.form_submit_button("Зарегистрироваться"):
                r = requests.post(
                    f"{API}/auth/register",
                    json={"email": email_s, "password": password_s},
                    timeout=5,
                )
                if r.status_code == 201:
                    st.session_state.token = r.json()["access_token"]
                    fetch_me()
                    st.rerun()
                else:
                    st.error(f"Ошибка: {r.json().get('detail', r.text)}")


# ─────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────
def render_sidebar():
    user = st.session_state.user
    with st.sidebar:
        st.markdown(f"**{user['email']}**")
        st.caption(f"Тариф: `{user['tariff']}`")
        st.metric("Кредиты (всего)", user["total_credits"])
        st.write(f"💸 Платные: {user['paid_credits']}  |  🎁 Бонус: {user['bonus_credits']}")

        st.divider()
        with st.expander("🎟 Промокод"):
            code = st.text_input("Введите код")
            if st.button("Активировать", key="promo_btn"):
                r = requests.post(
                    f"{API}/promo/activate",
                    json={"code": code}, headers=auth_headers(), timeout=5,
                )
                if r.status_code == 200:
                    st.success(r.json()["message"])
                    fetch_me()
                    st.rerun()
                else:
                    st.error(r.json().get("detail", r.text))

        with st.expander("💳 Пополнить баланс"):
            amt = st.number_input("Сумма", min_value=1, value=100, key="topup_amt")
            if st.button("Купить кредиты", key="topup_btn"):
                r = requests.post(
                    f"{API}/billing/topup",
                    json={"amount": int(amt)}, headers=auth_headers(), timeout=5,
                )
                if r.status_code == 200:
                    st.success(f"+{amt} кредитов")
                    fetch_me()
                    st.rerun()
                else:
                    st.error(r.text)

        st.divider()
        if st.button("Выйти"):
            st.session_state.token = None
            st.session_state.user = None
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────
# Предсказание
# ─────────────────────────────────────────────────────────────────────────
def render_predict_form():
    st.subheader("📊 Введите данные клиента")

    # Результат предыдущего предсказания показываем после rerun
    if "last_result" in st.session_state:
        kind, msg = st.session_state.pop("last_result")
        if kind == "success":
            st.success(msg)
        elif kind == "error":
            st.error(msg)
        else:
            st.warning(msg)

    DEFAULTS = {
        "ClientPeriod": 55, "MonthlySpending": 19.50, "TotalSpent": 1026.35,
        "Sex": "Male", "IsSeniorCitizen": 0, "HasPartner": "Yes", "HasChild": "Yes",
        "HasPhoneService": "Yes", "HasMultiplePhoneNumbers": "No",
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

    descr = pd.DataFrame([
        ("ClientPeriod", "Сколько месяцев клиент с нами", "0..72"),
        ("MonthlySpending", "Ежемесячные траты", "float"),
        ("TotalSpent", "Всего потрачено", "float"),
        ("Sex", "Пол", "Male / Female"),
        ("IsSeniorCitizen", "Пенсионер", "0 / 1"),
        ("HasPartner", "Есть партнёр", "Yes / No"),
        ("HasChild", "Есть ребёнок", "Yes / No"),
        ("HasPhoneService", "Телефония", "Yes / No"),
        ("HasMultiplePhoneNumbers", "Несколько номеров", "Yes / No / No phone service"),
        ("HasInternetService", "Тип интернета", "DSL / Fiber optic / No"),
        ("HasOnlineSecurityService", "Онлайн-безопасность", "Yes / No / No internet service"),
        ("HasOnlineBackup", "Онлайн-бэкап", "Yes / No / No internet service"),
        ("HasDeviceProtection", "Защита устройства", "Yes / No / No internet service"),
        ("HasTechSupportAccess", "Техподдержка", "Yes / No / No internet service"),
        ("HasOnlineTV", "ТВ", "Yes / No / No internet service"),
        ("HasMovieSubscription", "Кино-подписка", "Yes / No / No internet service"),
        ("HasContractPhone", "Тип контракта", "Month-to-month / One year / Two year"),
        ("IsBillingPaperless", "Безбумажный биллинг", "Yes / No"),
        ("PaymentMethod", "Способ оплаты", "Electronic check / Mailed check / Bank transfer / Credit card"),
    ], columns=["Поле", "Описание", "Допустимые значения"])

    with st.expander("📋 Описание полей", expanded=False):
        st.dataframe(descr, hide_index=True, use_container_width=True)

    YN = ["Yes", "No"]
    YN_NO_INET = ["Yes", "No", "No internet service"]
    YN_NO_PHONE = ["Yes", "No", "No phone service"]

    with st.form("predict_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            ClientPeriod = st.number_input("ClientPeriod", min_value=0, max_value=200, value=DEFAULTS["ClientPeriod"])
            MonthlySpending = st.number_input("MonthlySpending", min_value=0.0, value=DEFAULTS["MonthlySpending"])
            TotalSpent = st.number_input("TotalSpent", min_value=0.0, value=DEFAULTS["TotalSpent"])
            Sex = st.selectbox("Sex", ["Male", "Female"])
            IsSeniorCitizen = st.selectbox("IsSeniorCitizen", [0, 1])
            HasPartner = st.selectbox("HasPartner", YN)
            HasChild = st.selectbox("HasChild", YN)
        with c2:
            HasPhoneService = st.selectbox("HasPhoneService", YN)
            HasMultiplePhoneNumbers = st.selectbox("HasMultiplePhoneNumbers", YN_NO_PHONE, index=1)
            HasInternetService = st.selectbox("HasInternetService", ["DSL", "Fiber optic", "No"], index=2)
            HasOnlineSecurityService = st.selectbox("HasOnlineSecurityService", YN_NO_INET, index=2)
            HasOnlineBackup = st.selectbox("HasOnlineBackup", YN_NO_INET, index=2)
            HasDeviceProtection = st.selectbox("HasDeviceProtection", YN_NO_INET, index=2)
            HasTechSupportAccess = st.selectbox("HasTechSupportAccess", YN_NO_INET, index=2)
        with c3:
            HasOnlineTV = st.selectbox("HasOnlineTV", YN_NO_INET, index=2)
            HasMovieSubscription = st.selectbox("HasMovieSubscription", YN_NO_INET, index=2)
            HasContractPhone = st.selectbox("HasContractPhone", ["Month-to-month", "One year", "Two year"], index=1)
            IsBillingPaperless = st.selectbox("IsBillingPaperless", YN, index=1)
            PaymentMethod = st.selectbox(
                "PaymentMethod",
                ["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"],
                index=1,
            )

        submitted = st.form_submit_button("🚀 Предсказать (1 кредит)")

    if not submitted:
        return

    payload = {
        "ClientPeriod": int(ClientPeriod), "MonthlySpending": float(MonthlySpending),
        "TotalSpent": float(TotalSpent), "Sex": Sex,
        "IsSeniorCitizen": int(IsSeniorCitizen),
        "HasPartner": HasPartner, "HasChild": HasChild,
        "HasPhoneService": HasPhoneService,
        "HasMultiplePhoneNumbers": HasMultiplePhoneNumbers,
        "HasInternetService": HasInternetService,
        "HasOnlineSecurityService": HasOnlineSecurityService,
        "HasOnlineBackup": HasOnlineBackup,
        "HasDeviceProtection": HasDeviceProtection,
        "HasTechSupportAccess": HasTechSupportAccess,
        "HasOnlineTV": HasOnlineTV,
        "HasMovieSubscription": HasMovieSubscription,
        "HasContractPhone": HasContractPhone,
        "IsBillingPaperless": IsBillingPaperless,
        "PaymentMethod": PaymentMethod,
    }

    r = requests.post(f"{API}/ml/submit", json=payload, headers=auth_headers(), timeout=10)
    if r.status_code == 402:
        st.error(f"💳 Не хватает кредитов")
        return
    if r.status_code == 429:
        st.warning(f"⏱ Превышен лимит запросов")
        return
    if r.status_code != 202:
        st.error(f"Ошибка: {r.text}")
        return

    task_id = r.json()["task_id"]
    status_ph = st.empty()
    status_ph.info("Жду результат от модели...")

    for _ in range(20):
        time.sleep(0.7)
        rr = requests.get(f"{API}/ml/tasks/{task_id}", headers=auth_headers(), timeout=5)
        if rr.status_code != 200:
            continue
        data = rr.json()
        if data["status"] == "completed":
            res = data["result"]
            if res["reliable"] == 1:
                st.session_state["last_result"] = (
                    "success",
                    f"✅ Клиент НАДЁЖНЫЙ (вероятность оттока: {res['probability_churn']:.2%})",
                )
            else:
                st.session_state["last_result"] = (
                    "error",
                    f"⚠️ Клиент НЕНАДЁЖНЫЙ (вероятность оттока: {res['probability_churn']:.2%})",
                )
            time.sleep(0.5)   # небольшая пауза чтобы воркер успел записать транзакцию
            fetch_me()
            st.rerun()
            return
        if data["status"] == "failed":
            st.session_state["last_result"] = ("warning", f"Ошибка: {data['error']}")
            st.rerun()
            return
        status_ph.info(f"Статус: {data['status']}...")

    status_ph.warning("Превышено время ожидания. Проверь вкладку История.")


# ─────────────────────────────────────────────────────────────────────────
# История
# ─────────────────────────────────────────────────────────────────────────
def render_history():
    r = requests.get(f"{API}/ml/tasks?limit=20", headers=auth_headers(), timeout=5)
    if r.status_code != 200:
        st.warning("Не получилось загрузить историю")
        return

    tasks = r.json()
    if not tasks:
        st.caption("История пока пустая")
        return

    rows = []
    for t in tasks:
        result = t.get("result") or {}
        rows.append({
            "Создано": t["created_at"][:19].replace("T", " "),
            "Статус": t["status"],
            "Результат": "✅ Надёжный" if result.get("reliable") == 1 else ("❌ Ненадёжный" if result.get("reliable") == 0 else "—"),
            "P(churn)": f"{result.get('probability_churn', 0):.2%}" if result else "—",
            "Кредитов": t["credits_charged"],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────
# Админ-панель
# ─────────────────────────────────────────────────────────────────────────
def render_admin():
    st.subheader("🛠 Управление промокодами")

    # ── Создать промокод ──────────────────────────────────────────────
    with st.form("create_promo_form"):
        st.write("**Создать промокод**")
        col1, col2 = st.columns(2)
        with col1:
            code = st.text_input("Код промокода", placeholder="PROMO2025")
            bonus = st.number_input("Бонусных кредитов", min_value=1, value=50)
        with col2:
            max_act = st.number_input(
                "Макс. активаций (0 = безлимит)", min_value=0, value=0
            )
            valid_until = st.date_input("Действует до", value=None)

        if st.form_submit_button("➕ Создать"):
            body = {
                "code": code,
                "bonus_credits": int(bonus),
                "max_activations": int(max_act) if max_act > 0 else None,
                "valid_until": f"{valid_until}T23:59:59Z" if valid_until else None,
            }
            r = requests.post(
                f"{API}/admin/promo", json=body, headers=auth_headers(), timeout=5
            )
            if r.status_code == 201:
                st.success(f"Промокод **{code}** создан!")
                st.rerun()
            else:
                st.error(r.json().get("detail", r.text))

    st.divider()

    # ── Список промокодов ─────────────────────────────────────────────
    st.write("**Все промокоды**")
    r = requests.get(f"{API}/admin/promo", headers=auth_headers(), timeout=5)
    if r.status_code != 200:
        st.error("Не удалось загрузить список")
        return

    promos = r.json()
    if not promos:
        st.caption("Промокодов пока нет")
        return

    rows = []
    for p in promos:
        rows.append({
            "Код": p["code"],
            "Кредитов": p["bonus_credits"],
            "Активаций": f"{p['activations_count']} / {p['max_activations'] or '∞'}",
            "Активен": "✅" if p["is_active"] else "❌",
            "Действует до": p["valid_until"][:10] if p["valid_until"] else "—",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────
# Главная
# ─────────────────────────────────────────────────────────────────────────
def main():
    if not st.session_state.token or not fetch_me():
        render_login()
        return

    render_sidebar()

    user = st.session_state.user
    st.title("Churn Prediction")

    # Вкладка Админ видна только администратору
    if user.get("role") == "admin":
        tab1, tab2, tab3 = st.tabs(["Новое предсказание", "История", "⚙️ Админ"])
        with tab1:
            render_predict_form()
        with tab2:
            render_history()
        with tab3:
            render_admin()
    else:
        tab1, tab2 = st.tabs(["Новое предсказание", "История"])
        with tab1:
            render_predict_form()
        with tab2:
            render_history()


main()
