"""
Streamlit dashboard для жюри и автора проекта.

Запуск: streamlit run dashboard.py

Показывает: общая статистика, прирост компетенции (pre/post),
NPS-распределение, топ-сценарии, поведенческую воронку,
когортный retention, результаты A/B-тестов, лидерборд по XP.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent / "spas.db"))


@st.cache_data(ttl=60)
def load_table(name: str) -> pd.DataFrame:
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        if not cur.fetchone():
            return pd.DataFrame()
        return pd.read_sql_query(f"SELECT * FROM {name}", conn)


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="ISO8601", errors="coerce")


def _section_overview(
    users: pd.DataFrame,
    events: pd.DataFrame,
    feedback: pd.DataFrame,
    tests: pd.DataFrame,
) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Пользователей", len(users))
    completions = (events["name"] == "scenario_complete").sum() if not events.empty else 0
    col2.metric("Завершено сценариев", int(completions))
    avg_nps = float(feedback["nps"].mean()) if not feedback.empty and "nps" in feedback.columns else 0.0
    col3.metric("Средний NPS", f"{avg_nps:.1f}")
    if not tests.empty:
        pre = tests[tests.phase == "pre"]
        post = tests[tests.phase == "post"]
        pre_score = float((pre.correct / pre.total).mean()) if not pre.empty else 0.0
        post_score = float((post.correct / post.total).mean()) if not post.empty else 0.0
        col4.metric("Pre / Post (среднее)", f"{pre_score:.0%} → {post_score:.0%}")


def _section_daily(events: pd.DataFrame) -> None:
    st.subheader("События по дням")
    if events.empty:
        st.info("Нет событий — дождись первых пользователей.")
        return
    ev = events.copy()
    ev["ts"] = _to_datetime(ev["ts"])
    ev = ev.dropna(subset=["ts"])
    daily = ev.groupby([ev["ts"].dt.date, "name"]).size().unstack(fill_value=0)
    st.line_chart(daily)


def _section_top_scenarios(events: pd.DataFrame) -> None:
    st.subheader("Топ-10 сценариев (открытий)")
    if events.empty:
        return
    opens = events[events["name"] == "scenario_open"]
    if opens.empty:
        st.info("Никто пока не открывал сценарии.")
        return
    top = opens["payload"].value_counts().head(10)
    st.bar_chart(top)


def _section_funnel(events: pd.DataFrame) -> None:
    st.subheader("Поведенческая воронка")
    st.caption("От первого старта до сертификата. Уникальные пользователи на каждом шаге.")
    if events.empty:
        st.info("Пока нет данных.")
        return
    steps = [
        ("start", "Запустили /start"),
        ("scenario_open", "Открыли сценарий"),
        ("scenario_complete", "Дочитали сценарий"),
        ("nps", "Поставили NPS"),
        ("certificate_issued", "Получили сертификат"),
    ]
    rows = []
    for name, label in steps:
        n = int(events[events["name"] == name]["user_id"].nunique())
        rows.append({"Шаг": label, "Уникальные пользователи": n})
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.bar_chart(df.set_index("Шаг")["Уникальные пользователи"])


def _section_cohort(events: pd.DataFrame) -> None:
    st.subheader("Когортный retention по неделям")
    st.caption(
        "Когорта — неделя первой активности пользователя. "
        "Цифра в колонке `N` — доля когорты, вернувшаяся через N недель."
    )
    if events.empty:
        st.info("Когортный анализ доступен после первых пользователей.")
        return
    ev = events.copy()
    ev["ts"] = _to_datetime(ev["ts"])
    ev = ev.dropna(subset=["ts"])
    if ev.empty:
        return
    first = ev.groupby("user_id")["ts"].min().rename("first_seen")
    ev = ev.join(first, on="user_id")
    ev["cohort"] = ev["first_seen"].dt.to_period("W").apply(lambda p: p.start_time.date())
    ev["week_offset"] = ((ev["ts"] - ev["first_seen"]).dt.days // 7).astype(int)
    grouped = ev.groupby(["cohort", "week_offset"])["user_id"].nunique().unstack(fill_value=0).sort_index()
    if grouped.empty or 0 not in grouped.columns:
        st.info("Слишком мало данных для когорт.")
        return
    cohort_size = grouped[0].replace(0, 1)
    retention = (grouped.div(cohort_size, axis=0) * 100).round(0)
    st.dataframe(retention.style.format("{:.0f}%"), use_container_width=True)


def _section_nps_heatmap(feedback: pd.DataFrame) -> None:
    st.subheader("NPS-хитмэп: распределение голосов по неделям")
    if feedback.empty or "nps" not in feedback.columns:
        st.info("Нет NPS-голосов.")
        return
    fb = feedback.copy()
    fb["ts"] = _to_datetime(fb["ts"])
    fb = fb.dropna(subset=["ts", "nps"])
    if fb.empty:
        return
    fb["week"] = fb["ts"].dt.to_period("W").apply(lambda p: p.start_time.date())
    pivot = fb.pivot_table(index="nps", columns="week", values="user_id", aggfunc="count", fill_value=0)
    pivot = pivot.sort_index(ascending=False)
    st.dataframe(pivot, use_container_width=True)


def _section_pre_post(tests: pd.DataFrame) -> None:
    st.subheader("Прирост компетенции по сценариям")
    if tests.empty:
        st.info("Нет тестов.")
        return
    df = tests.copy()
    df["score"] = df["correct"] / df["total"].replace(0, 1)
    by_scenario = (
        df.groupby(["scenario_id", "phase"])["score"].mean().unstack("phase", fill_value=0).reset_index()
    )
    if "pre" in by_scenario.columns and "post" in by_scenario.columns:
        by_scenario["delta"] = (by_scenario["post"] - by_scenario["pre"]).round(2)
        by_scenario = by_scenario.sort_values("delta", ascending=False)
        st.dataframe(
            by_scenario.style.format({"pre": "{:.0%}", "post": "{:.0%}", "delta": "{:+.0%}"}),
            use_container_width=True,
            hide_index=True,
        )


def _section_ab(ab: pd.DataFrame, events: pd.DataFrame) -> None:
    st.subheader("A/B-тесты")
    if ab.empty:
        st.info(
            "Нет назначенных A/B-вариантов. Использование: "
            "`await storage.assign_ab_variant(user_id, 'experiment', 'A'|'B')`."
        )
        return
    if events.empty:
        st.dataframe(ab, use_container_width=True)
        return
    completions = events[events["name"] == "scenario_complete"]
    completed_users = set(completions["user_id"].astype(int).tolist())
    rows = []
    for (exp, variant), df in ab.groupby(["experiment", "variant"]):
        users = set(df["user_id"].astype(int).tolist())
        rows.append(
            {
                "experiment": exp,
                "variant": variant,
                "users": len(users),
                "completed": len(users & completed_users),
                "completion_rate": (len(users & completed_users) / len(users) if users else 0.0),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        st.dataframe(
            out.style.format({"completion_rate": "{:.0%}"}),
            use_container_width=True,
            hide_index=True,
        )


def _section_xp(xp: pd.DataFrame) -> None:
    st.subheader("Лидерборд XP")
    if xp.empty:
        st.info("Никто пока не зарабатывал XP.")
        return
    df = xp.sort_values("xp", ascending=False).head(20)
    cols = [c for c in ["user_id", "xp", "level", "streak_days", "last_active"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="СПАС — дашборд", layout="wide")
    st.title("📊 СПАС — дашборд проекта")
    st.caption("AI-помощник первой помощи для подростков 14–17 лет")

    users = load_table("users")
    events = load_table("events")
    feedback = load_table("feedback")
    tests = load_table("test_results")
    ab = load_table("ab_assignments")
    xp = load_table("user_xp")

    if users.empty:
        st.info("Нет данных. Запусти бот и попроси нескольких людей пройти сценарий.")
        return

    _section_overview(users, events, feedback, tests)
    _section_daily(events)
    _section_top_scenarios(events)
    _section_funnel(events)
    _section_cohort(events)
    _section_nps_heatmap(feedback)
    _section_pre_post(tests)
    _section_ab(ab, events)
    _section_xp(xp)


if __name__ == "__main__":
    main()
