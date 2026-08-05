
import sqlite3
from datetime import date, datetime
from pathlib import Path
import math

import pandas as pd
import streamlit as st

APP_NAME = "AI Football Quant Pro"
DB_PATH = Path("football_quant.db")

st.set_page_config(
    page_title=APP_NAME,
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 4rem; max-width: 1150px;}
[data-testid="stMetric"] {
    background: linear-gradient(180deg, rgba(22,29,39,.95), rgba(12,18,25,.95));
    border: 1px solid rgba(80,160,255,.26);
    border-radius: 16px;
    padding: 14px;
}
[data-testid="stMetricValue"] {font-size: 1.75rem;}
div[data-testid="stDataFrame"] {border-radius: 14px; overflow: hidden;}
.stButton > button {
    width: 100%;
    border-radius: 12px;
    min-height: 44px;
    font-weight: 700;
}
section[data-testid="stSidebar"] {width: 300px !important;}
@media (max-width: 768px) {
    .block-container {padding-left: .75rem; padding-right: .75rem;}
    [data-testid="column"] {min-width: 100% !important; flex: 1 1 100% !important;}
    [data-testid="stMetricValue"] {font-size: 1.45rem;}
}
</style>
""", unsafe_allow_html=True)


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        match_date TEXT NOT NULL,
        league TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        market TEXT NOT NULL,
        selection TEXT NOT NULL,
        line REAL,
        odds REAL NOT NULL,
        stake REAL NOT NULL,
        strategy TEXT NOT NULL,
        model_probability REAL,
        result_status TEXT NOT NULL DEFAULT '未结算',
        profit REAL NOT NULL DEFAULT 0,
        notes TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bankroll (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        initial_balance REAL NOT NULL
    )
    """)
    cur.execute("INSERT OR IGNORE INTO bankroll (id, initial_balance) VALUES (1, 10000)")
    conn.commit()
    conn.close()


def fetch_df(query, params=()):
    conn = connect()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def execute(query, params=()):
    conn = connect()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()


def settle_profit(status, stake, odds):
    mapping = {
        "全赢": stake * (odds - 1),
        "半赢": stake * (odds - 1) / 2,
        "走盘": 0.0,
        "半输": -stake / 2,
        "全输": -stake,
        "未结算": 0.0,
    }
    return round(mapping[status], 2)


def max_drawdown(equity_series):
    if equity_series.empty:
        return 0.0
    running_max = equity_series.cummax()
    dd = (equity_series - running_max) / running_max.replace(0, pd.NA)
    return float(dd.min() * 100) if not dd.empty else 0.0


def kelly_fraction(probability, odds):
    if probability is None or odds <= 1:
        return 0.0
    p = probability / 100
    b = odds - 1
    q = 1 - p
    full = (b * p - q) / b
    return max(0.0, full)


init_db()

with st.sidebar:
    st.title("⚽ Quant Pro")
    page = st.radio(
        "导航",
        ["首页仪表盘", "新增投注", "赛果结算", "投注记录", "策略分析", "资金设置"],
        label_visibility="collapsed",
    )
    st.caption("默认货币：RM 马币")

bets = fetch_df("SELECT * FROM bets ORDER BY match_date, id")
initial_balance = float(fetch_df("SELECT initial_balance FROM bankroll WHERE id=1").iloc[0,0])

if not bets.empty:
    bets["match_date"] = pd.to_datetime(bets["match_date"])
    bets["created_at"] = pd.to_datetime(bets["created_at"])
    bets["profit"] = pd.to_numeric(bets["profit"], errors="coerce").fillna(0)
    settled = bets[bets["result_status"] != "未结算"].copy()
else:
    settled = pd.DataFrame()

current_balance = initial_balance + (settled["profit"].sum() if not settled.empty else 0)
roi = ((current_balance / initial_balance) - 1) * 100 if initial_balance else 0

if page == "首页仪表盘":
    st.title("AI Football Quant Pro")
    st.caption("数据驱动 · 概率建模 · 风险控制 · 默认货币 RM")

    if not settled.empty:
        win_equiv = settled["result_status"].map({
            "全赢": 1, "半赢": 0.5, "走盘": 0, "半输": 0, "全输": 0
        }).sum()
        hit_rate = win_equiv / len(settled) * 100
        settled = settled.sort_values(["match_date", "id"])
        settled["equity"] = initial_balance + settled["profit"].cumsum()
        mdd = max_drawdown(settled["equity"])
        daily = settled.groupby(settled["match_date"].dt.date)["profit"].sum()
        profitable_days = (daily > 0).mean() * 100 if len(daily) else 0
    else:
        hit_rate = mdd = profitable_days = 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("当前资金", f"RM {current_balance:,.2f}", f"{roi:+.1f}%")
    c2.metric("综合命中率", f"{hit_rate:.1f}%")
    c3.metric("最大回撤", f"{mdd:.1f}%")
    c4.metric("盈利天数占比", f"{profitable_days:.1f}%")

    st.subheader("资金增长曲线")
    if not settled.empty:
        chart = settled.set_index("match_date")[["equity"]]
        st.line_chart(chart, height=330)
    else:
        st.info("还没有已结算投注。先到“新增投注”录入记录。")

    st.subheader("每日盈亏")
    if not settled.empty:
        daily_chart = settled.groupby(settled["match_date"].dt.date)["profit"].sum().to_frame()
        st.bar_chart(daily_chart, height=300)

    st.subheader("最近投注")
    recent = bets.sort_values("created_at", ascending=False).head(10).copy() if not bets.empty else pd.DataFrame()
    if not recent.empty:
        recent["比赛"] = recent["home_team"] + " vs " + recent["away_team"]
        show = recent[["match_date","league","比赛","market","selection","odds","stake","result_status","profit"]]
        show.columns = ["日期","联赛","比赛","市场","选择","赔率","注额(RM)","结果","盈亏(RM)"]
        st.dataframe(show, use_container_width=True, hide_index=True)
    else:
        st.info("暂无投注记录。")

elif page == "新增投注":
    st.title("新增投注")
    st.caption("支持单关记录；串关可先按整张票作为一条记录录入。")

    with st.form("add_bet", clear_on_submit=True):
        a, b = st.columns(2)
        with a:
            match_date = st.date_input("比赛日期", value=date.today())
            league = st.text_input("联赛 / 杯赛", placeholder="例如：巴甲、欧冠资格赛")
            home = st.text_input("主队")
            away = st.text_input("客队")
            market = st.selectbox("投注市场", [
                "亚洲让球", "全场大小", "上半场大小", "独赢", "平局", "双重机会", "比分", "串关"
            ])
        with b:
            selection = st.text_input("投注选择", placeholder="例如：小3.0、客队+1、上半场小1.25")
            line = st.number_input("盘口线（没有可填0）", value=0.0, step=0.25)
            odds = st.number_input("赔率", min_value=1.01, value=1.90, step=0.01)
            stake = st.number_input("投注金额 RM", min_value=1.0, value=100.0, step=10.0)
            strategy = st.selectbox("策略分类", [
                "正常策略", "冷门策略", "平局策略", "平衡策略",
                "上半场策略", "大小球策略", "让球策略", "串关策略"
            ])

        model_probability = st.slider("模型命中概率（%）", 0.0, 100.0, 55.0, 0.5)
        implied = 100 / odds
        ev = model_probability / 100 * odds - 1
        kelly = kelly_fraction(model_probability, odds)
        st.info(
            f"市场隐含概率：{implied:.1f}% ｜ 模型EV：{ev*100:+.1f}% ｜ "
            f"全Kelly：{kelly*100:.1f}% ｜ 建议1/4 Kelly：{kelly*25:.1f}%"
        )
        notes = st.text_area("备注", placeholder="首发、伤停、轮换、盘口变化、风险说明等")
        submitted = st.form_submit_button("保存投注")

        if submitted:
            required = [league.strip(), home.strip(), away.strip(), selection.strip()]
            if not all(required):
                st.error("请完整填写联赛、主队、客队和投注选择。")
            else:
                execute("""
                INSERT INTO bets (
                    created_at, match_date, league, home_team, away_team, market,
                    selection, line, odds, stake, strategy, model_probability, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(timespec="seconds"),
                    match_date.isoformat(), league.strip(), home.strip(), away.strip(),
                    market, selection.strip(), line, odds, stake, strategy,
                    model_probability, notes.strip()
                ))
                st.success("投注已保存。")

elif page == "赛果结算":
    st.title("赛果结算")
    pending = fetch_df("SELECT * FROM bets WHERE result_status='未结算' ORDER BY match_date, id")
    if pending.empty:
        st.info("目前没有待结算投注。")
    else:
        pending["label"] = pending.apply(
            lambda r: f"#{r['id']}｜{r['match_date']}｜{r['home_team']} vs {r['away_team']}｜{r['selection']} @ {r['odds']}",
            axis=1
        )
        selected_label = st.selectbox("选择投注", pending["label"].tolist())
        row = pending[pending["label"] == selected_label].iloc[0]
        st.write(f"注额：**RM {row['stake']:.2f}**")
        status = st.selectbox("结算结果", ["全赢", "半赢", "走盘", "半输", "全输"])
        profit = settle_profit(status, float(row["stake"]), float(row["odds"]))
        st.metric("本单盈亏", f"RM {profit:+,.2f}")
        if st.button("确认结算"):
            execute(
                "UPDATE bets SET result_status=?, profit=? WHERE id=?",
                (status, profit, int(row["id"]))
            )
            st.success("结算完成，请刷新或切换页面查看最新数据。")

elif page == "投注记录":
    st.title("投注记录")
    if bets.empty:
        st.info("暂无记录。")
    else:
        data = bets.copy()
        data["比赛"] = data["home_team"] + " vs " + data["away_team"]
        show = data[[
            "id","match_date","league","比赛","market","selection","line","odds",
            "stake","strategy","model_probability","result_status","profit","notes"
        ]]
        show.columns = [
            "ID","日期","联赛","比赛","市场","选择","盘口","赔率","注额(RM)",
            "策略","模型概率%","结果","盈亏(RM)","备注"
        ]
        st.dataframe(show.sort_values(["日期","ID"], ascending=False), use_container_width=True, hide_index=True)

        st.subheader("删除记录")
        delete_id = st.number_input("输入要删除的ID", min_value=0, step=1)
        if st.button("删除"):
            if delete_id <= 0:
                st.error("请输入有效ID。")
            else:
                execute("DELETE FROM bets WHERE id=?", (int(delete_id),))
                st.success("记录已删除。")

elif page == "策略分析":
    st.title("策略分析")
    if settled.empty:
        st.info("需要先结算一些投注。")
    else:
        def strategy_summary(group):
            stake_sum = group["stake"].sum()
            profit_sum = group["profit"].sum()
            wins = group["result_status"].map({
                "全赢": 1, "半赢": 0.5, "走盘": 0, "半输": 0, "全输": 0
            }).sum()
            return pd.Series({
                "投注数": len(group),
                "等效命中": wins,
                "命中率%": wins / len(group) * 100 if len(group) else 0,
                "总投注RM": stake_sum,
                "总盈亏RM": profit_sum,
                "ROI%": profit_sum / stake_sum * 100 if stake_sum else 0
            })

        by_strategy = settled.groupby("strategy").apply(strategy_summary).reset_index()
        by_league = settled.groupby("league").apply(strategy_summary).reset_index()

        st.subheader("四类及扩展策略")
        st.dataframe(by_strategy.round(2), use_container_width=True, hide_index=True)

        st.subheader("联赛独立统计")
        st.dataframe(by_league.round(2), use_container_width=True, hide_index=True)

elif page == "资金设置":
    st.title("资金设置")
    st.metric("当前初始资金", f"RM {initial_balance:,.2f}")
    new_balance = st.number_input(
        "设置初始资金 RM",
        min_value=100.0,
        value=float(initial_balance),
        step=100.0
    )
    if st.button("保存资金设置"):
        execute("UPDATE bankroll SET initial_balance=? WHERE id=1", (new_balance,))
        st.success("初始资金已更新。")

    st.subheader("建议风控")
    st.write("""
- 单注建议：本金的 1%–3%
- 高EV但高波动策略：最多 1/4 Kelly
- 每日止损：本金的 5%–8%
- 串关与单关分开统计
- 不同联赛独立查看 ROI，不用一个联赛的结果修正另一个联赛
    """)
