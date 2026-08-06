
from __future__ import annotations

from datetime import date, datetime, timezone
from itertools import combinations
import math
from typing import Any

import pandas as pd
import requests
import streamlit as st

APP_NAME = "AI Football Quant Pro V10"
st.set_page_config(
    page_title=APP_NAME,
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container{padding-top:.7rem;padding-bottom:5rem;max-width:1180px}
[data-testid="stMetric"]{background:#101823;border:1px solid #24496e;border-radius:18px;padding:16px}
[data-testid="stMetricValue"]{font-size:1.55rem}
.stButton>button{width:100%;min-height:44px;border-radius:12px;font-weight:700}
.quant-card{background:#101823;border:1px solid #24496e;border-radius:18px;padding:16px;margin:10px 0}
.good{border-color:#22865d}.warn{border-color:#a8822d}.bad{border-color:#a64242}
.small{font-size:.86rem;color:#9ca3af}
@media(max-width:768px){
.block-container{padding-left:.7rem;padding-right:.7rem}
[data-testid="column"]{min-width:100%!important;flex:1 1 100%!important}
[data-testid="stMetricValue"]{font-size:1.35rem}
}
</style>
""", unsafe_allow_html=True)

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].rstrip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("尚未配置 SUPABASE_URL 和 SUPABASE_KEY。请到 Streamlit Manage app → Settings → Secrets 保存。")
    st.stop()


def api_headers(access_token: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    headers["Authorization"] = f"Bearer {access_token or SUPABASE_KEY}"
    return headers


def auth_request(path: str, payload: dict[str, Any], params: dict[str, str] | None = None) -> dict[str, Any]:
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/{path}",
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
        params=params,
        json=payload,
        timeout=30,
    )
    if not response.ok:
        try:
            detail = response.json().get("msg") or response.json().get("error_description") or response.text
        except Exception:
            detail = response.text
        raise RuntimeError(detail)
    return response.json()


def rest_get(table: str, token: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=api_headers(token),
        params=params or {},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(response.text)
    return response.json()


def rest_insert(table: str, token: str, rows: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    headers = api_headers(token)
    headers["Prefer"] = "return=representation"
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        json=rows,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(response.text)
    return response.json()


def rest_patch(table: str, token: str, filters: dict[str, str], payload: dict[str, Any]) -> list[dict[str, Any]]:
    headers = api_headers(token)
    headers["Prefer"] = "return=representation"
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=filters,
        json=payload,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(response.text)
    return response.json()


def rest_delete(table: str, token: str, filters: dict[str, str]) -> None:
    response = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=api_headers(token),
        params=filters,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(response.text)


def utc_iso(d: date, hour: int = 12) -> str:
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=timezone.utc).isoformat()


def settle_profit(status: str, stake: float, odds: float) -> float:
    return round({
        "full_win": stake * (odds - 1),
        "half_win": stake * (odds - 1) / 2,
        "push": 0.0,
        "half_loss": -stake / 2,
        "full_loss": -stake,
        "void": 0.0,
        "pending": 0.0,
    }[status], 2)


def kelly_fraction(probability: float, odds: float) -> float:
    if odds <= 1:
        return 0.0
    p = probability / 100
    b = odds - 1
    return max(0.0, (b * p - (1 - p)) / b)


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = (equity - peak) / peak.replace(0, pd.NA)
    return float(dd.min() * 100)


def login_screen() -> None:
    st.title("⚽ AI Football Quant Pro V10")
    st.caption("云端数据库 · RM资金管理 · 联赛独立模型")

    login_tab, signup_tab = st.tabs(["登录", "注册"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("密码", type="password")
            submit = st.form_submit_button("登录")
        if submit:
            try:
                result = auth_request(
                    "token",
                    {"email": email.strip(), "password": password},
                    params={"grant_type": "password"},
                )
                st.session_state["access_token"] = result["access_token"]
                st.session_state["refresh_token"] = result.get("refresh_token")
                st.session_state["user"] = result["user"]
                st.rerun()
            except Exception as exc:
                st.error(f"登录失败：{exc}")

    with signup_tab:
        with st.form("signup_form"):
            email = st.text_input("注册Email", key="signup_email")
            password = st.text_input("设置密码（至少6位）", type="password", key="signup_password")
            display_name = st.text_input("显示名称", value="CKY")
            submit = st.form_submit_button("注册")
        if submit:
            try:
                result = auth_request(
                    "signup",
                    {
                        "email": email.strip(),
                        "password": password,
                        "data": {"display_name": display_name.strip()},
                    },
                )
                if result.get("access_token"):
                    st.session_state["access_token"] = result["access_token"]
                    st.session_state["refresh_token"] = result.get("refresh_token")
                    st.session_state["user"] = result["user"]
                    st.rerun()
                else:
                    st.success("注册成功。请到Email完成确认后再登录。")
            except Exception as exc:
                st.error(f"注册失败：{exc}")


if "access_token" not in st.session_state or "user" not in st.session_state:
    login_screen()
    st.stop()

token: str = st.session_state["access_token"]
user: dict[str, Any] = st.session_state["user"]
user_id = user["id"]

with st.sidebar:
    st.title("⚽ Quant Pro V10")
    st.caption(user.get("email", ""))
    page = st.radio(
        "导航",
        [
            "首页",
            "今日赛事",
            "赛前预测",
            "投注中心",
            "串关生成器",
            "赛果结算",
            "赛后复盘",
            "联赛模型",
            "报表中心",
            "系统设置",
        ],
        label_visibility="collapsed",
    )
    if st.button("退出登录"):
        st.session_state.clear()
        st.rerun()


@st.cache_data(ttl=20, show_spinner=False)
def load_bankroll(token_value: str) -> list[dict[str, Any]]:
    return rest_get(
        "bankrolls",
        token_value,
        {"select": "*", "is_active": "eq.true", "order": "created_at.asc", "limit": "1"},
    )


@st.cache_data(ttl=20, show_spinner=False)
def load_matches(token_value: str) -> list[dict[str, Any]]:
    return rest_get("matches", token_value, {"select": "*", "order": "match_date.desc", "limit": "300"})


@st.cache_data(ttl=20, show_spinner=False)
def load_predictions(token_value: str) -> list[dict[str, Any]]:
    return rest_get("predictions", token_value, {"select": "*", "order": "created_at.desc", "limit": "300"})


@st.cache_data(ttl=20, show_spinner=False)
def load_bets(token_value: str) -> list[dict[str, Any]]:
    return rest_get("bets", token_value, {"select": "*", "order": "bet_date.desc", "limit": "1000"})


@st.cache_data(ttl=20, show_spinner=False)
def load_models(token_value: str) -> list[dict[str, Any]]:
    return rest_get("league_models", token_value, {"select": "*", "order": "league_name.asc"})


def clear_cache() -> None:
    st.cache_data.clear()


try:
    bankroll_rows = load_bankroll(token)
    match_rows = load_matches(token)
    prediction_rows = load_predictions(token)
    bet_rows = load_bets(token)
except Exception as exc:
    st.error(f"读取云端数据库失败：{exc}")
    st.stop()

bankroll = bankroll_rows[0] if bankroll_rows else None
matches_df = pd.DataFrame(match_rows)
pred_df = pd.DataFrame(prediction_rows)
bets_df = pd.DataFrame(bet_rows)

if not matches_df.empty:
    matches_df["match_date"] = pd.to_datetime(matches_df["match_date"], utc=True, errors="coerce")
if not bets_df.empty:
    bets_df["bet_date"] = pd.to_datetime(bets_df["bet_date"], utc=True, errors="coerce")
    bets_df["stake"] = pd.to_numeric(bets_df["stake"], errors="coerce").fillna(0)
    bets_df["profit"] = pd.to_numeric(bets_df["profit"], errors="coerce").fillna(0)
    bets_df["odds"] = pd.to_numeric(bets_df["odds"], errors="coerce").fillna(0)

initial_balance = float(bankroll["initial_balance"]) if bankroll else 10000.0
settled = bets_df[bets_df["result_status"] != "pending"].copy() if not bets_df.empty else pd.DataFrame()
profit_total = float(settled["profit"].sum()) if not settled.empty else 0.0
current_balance = initial_balance + profit_total


if page == "首页":
    st.title("AI Football Quant Pro V10")
    st.caption("云端数据库 · RM资金管理 · 赛前预测 · 串关 · 复盘")

    roi = (profit_total / initial_balance * 100) if initial_balance else 0.0
    if not settled.empty:
        equivalent_wins = settled["result_status"].map({
            "full_win": 1.0, "half_win": 0.5,
            "push": 0.0, "half_loss": 0.0,
            "full_loss": 0.0, "void": 0.0,
        }).fillna(0).sum()
        hit_rate = equivalent_wins / len(settled) * 100
        settled = settled.sort_values("bet_date")
        settled["equity"] = initial_balance + settled["profit"].cumsum()
        mdd = max_drawdown(settled["equity"])
        daily = settled.groupby(settled["bet_date"].dt.date)["profit"].sum()
        profitable_days = (daily > 0).mean() * 100 if len(daily) else 0.0
    else:
        hit_rate = mdd = profitable_days = 0.0
        daily = pd.Series(dtype=float)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("当前资金", f"RM {current_balance:,.2f}", f"{roi:+.1f}%")
    c2.metric("综合命中率", f"{hit_rate:.1f}%")
    c3.metric("最大回撤", f"{mdd:.1f}%")
    c4.metric("盈利天数", f"{profitable_days:.1f}%")

    st.subheader("资金增长曲线")
    if not settled.empty:
        st.line_chart(settled.set_index("bet_date")[["equity"]], height=320)
    else:
        st.info("暂无已结算投注。")

    st.subheader("每日盈亏")
    if not daily.empty:
        st.bar_chart(daily.to_frame("profit"), height=260)


elif page == "今日赛事":
    st.title("今日赛事")
    today = pd.Timestamp.now(tz="UTC").date()
    if matches_df.empty:
        st.info("尚未录入赛事。")
    else:
        today_matches = matches_df[matches_df["match_date"].dt.date == today].copy()
        if today_matches.empty:
            st.info("今天没有已录入赛事。")
        else:
            show = today_matches[[
                "match_date", "competition", "home_team", "away_team", "status",
                "home_score", "away_score"
            ]].copy()
            show.columns = ["时间", "赛事", "主队", "客队", "状态", "主队比分", "客队比分"]
            st.dataframe(show, use_container_width=True, hide_index=True)

    st.subheader("新增赛事")
    with st.form("new_match", clear_on_submit=True):
        a, b = st.columns(2)
        with a:
            md = st.date_input("比赛日期", date.today())
            competition = st.text_input("联赛/杯赛")
            country = st.text_input("国家/地区")
            home = st.text_input("主队")
        with b:
            away = st.text_input("客队")
            venue = st.text_input("场地")
            neutral = st.checkbox("中立场")
            notes = st.text_area("备注")
        submit = st.form_submit_button("保存赛事")
        if submit:
            if not all([competition.strip(), home.strip(), away.strip()]):
                st.error("请填写赛事、主队和客队。")
            else:
                try:
                    rest_insert("matches", token, {
                        "user_id": user_id,
                        "match_date": utc_iso(md),
                        "competition": competition.strip(),
                        "country": country.strip() or None,
                        "home_team": home.strip(),
                        "away_team": away.strip(),
                        "venue": venue.strip() or None,
                        "neutral_venue": neutral,
                        "notes": notes.strip() or None,
                    })
                    clear_cache()
                    st.success("赛事已保存。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存失败：{exc}")


elif page == "赛前预测":
    st.title("赛前预测")
    if matches_df.empty:
        st.info("请先在“今日赛事”新增比赛。")
    else:
        selectable = matches_df.copy()
        selectable["label"] = selectable.apply(
            lambda r: f"{r['match_date'].date()}｜{r['competition']}｜{r['home_team']} vs {r['away_team']}",
            axis=1,
        )
        with st.form("prediction_form", clear_on_submit=True):
            selected_label = st.selectbox("比赛", selectable["label"].tolist())
            row = selectable[selectable["label"] == selected_label].iloc[0]
            a, b = st.columns(2)
            with a:
                home_prob = st.slider("主胜概率%", 0.0, 100.0, 45.0, 0.5)
                draw_prob = st.slider("平局概率%", 0.0, 100.0, 28.0, 0.5)
                away_prob = st.slider("客胜概率%", 0.0, 100.0, 27.0, 0.5)
                exp_home = st.number_input("主队预计进球", 0.0, 8.0, 1.30, 0.05)
                exp_away = st.number_input("客队预计进球", 0.0, 8.0, 1.05, 0.05)
            with b:
                first_half = st.number_input("上半场预计总进球", 0.0, 4.0, 1.00, 0.05)
                confidence = st.slider("综合信心%", 0.0, 100.0, 60.0, 1.0)
                upset = st.slider("爆冷风险%", 0.0, 100.0, 25.0, 1.0)
                score1 = st.text_input("比分1", "1-0")
                score2 = st.text_input("比分2", "1-1")
                score3 = st.text_input("比分3", "2-0")

            recommended_market = st.selectbox(
                "推荐市场",
                ["亚洲让球", "全场大小", "上半场大小", "独赢", "平局", "比分", "暂不下注"],
            )
            recommended_selection = st.text_input("推荐选择", placeholder="例如：上半场小1.25")
            recommended_line = st.number_input("推荐盘口线", value=0.0, step=0.25)
            notes = st.text_area("分析备注")
            submit = st.form_submit_button("保存预测")

        if submit:
            total = home_prob + draw_prob + away_prob
            if abs(total - 100) > 0.6:
                st.error("主胜、平局和客胜概率合计必须接近100%。")
            else:
                total_goals = exp_home + exp_away
                try:
                    existing = rest_get(
                        "predictions",
                        token,
                        {
                            "select": "id",
                            "match_id": f"eq.{row['id']}",
                            "model_version": "eq.V10",
                            "limit": "1",
                        },
                    )
                    payload = {
                        "user_id": user_id,
                        "match_id": row["id"],
                        "model_version": "V10",
                        "home_win_probability": home_prob,
                        "draw_probability": draw_prob,
                        "away_win_probability": away_prob,
                        "expected_home_goals": exp_home,
                        "expected_away_goals": exp_away,
                        "expected_total_goals": total_goals,
                        "expected_first_half_goals": first_half,
                        "confidence": confidence,
                        "upset_risk": upset,
                        "aos_flag": max(exp_home, exp_away) >= 5,
                        "score_1": score1.strip(),
                        "score_2": score2.strip(),
                        "score_3": score3.strip(),
                        "recommended_market": recommended_market,
                        "recommended_selection": recommended_selection.strip() or None,
                        "recommended_line": recommended_line,
                        "notes": notes.strip() or None,
                    }
                    if existing:
                        rest_patch("predictions", token, {"id": f"eq.{existing[0]['id']}"}, payload)
                    else:
                        rest_insert("predictions", token, payload)
                    clear_cache()
                    st.success("预测已保存到云端。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存失败：{exc}")


elif page == "投注中心":
    st.title("投注中心")

    if matches_df.empty:
        st.info("请先新增赛事。")
    else:
        selectable = matches_df.copy()
        selectable["label"] = selectable.apply(
            lambda r: f"{r['match_date'].date()}｜{r['home_team']} vs {r['away_team']}",
            axis=1,
        )
        with st.form("bet_form", clear_on_submit=True):
            label = st.selectbox("比赛", selectable["label"].tolist())
            row = selectable[selectable["label"] == label].iloc[0]
            a, b = st.columns(2)
            with a:
                market = st.selectbox("市场", ["亚洲让球", "全场大小", "上半场大小", "独赢", "平局", "比分"])
                selection = st.text_input("选择")
                line = st.number_input("盘口线", value=0.0, step=0.25)
                odds = st.number_input("赔率", min_value=1.01, value=1.90, step=0.01)
            with b:
                stake = st.number_input("注额 RM", min_value=1.0, value=100.0, step=10.0)
                probability = st.slider("模型概率%", 0.0, 100.0, 55.0, 0.5)
                strategy = st.selectbox(
                    "策略",
                    ["normal", "upset", "draw", "balanced", "first_half", "totals", "handicap"],
                )
                notes = st.text_area("备注")
            ev = probability / 100 * odds - 1
            kelly = kelly_fraction(probability, odds)
            st.info(f"隐含概率 {100/odds:.1f}%｜EV {ev*100:+.1f}%｜1/4 Kelly {kelly*25:.1f}%")
            submit = st.form_submit_button("保存投注")

        if submit:
            if not selection.strip():
                st.error("请填写投注选择。")
            else:
                try:
                    rest_insert("bets", token, {
                        "user_id": user_id,
                        "bankroll_id": bankroll["id"] if bankroll else None,
                        "match_id": row["id"],
                        "market": market,
                        "selection": selection.strip(),
                        "line": line,
                        "odds": odds,
                        "stake": stake,
                        "model_probability": probability,
                        "ev_percent": ev * 100,
                        "kelly_fraction": kelly,
                        "strategy": strategy,
                        "notes": notes.strip() or None,
                    })
                    clear_cache()
                    st.success("投注已保存。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存失败：{exc}")

    st.subheader("最近投注")
    if bets_df.empty:
        st.info("暂无投注记录。")
    else:
        st.dataframe(
            bets_df[[
                "bet_date", "market", "selection", "line", "odds", "stake",
                "strategy", "result_status", "profit"
            ]],
            use_container_width=True,
            hide_index=True,
        )


elif page == "串关生成器":
    st.title("串关生成器")
    if bets_df.empty:
        st.info("请先录入单关候选。")
    else:
        pending = bets_df[bets_df["result_status"] == "pending"].copy()
        pending = pending[
            (pending["model_probability"].fillna(0) >= 52) &
            (pending["ev_percent"].fillna(-999) > 0)
        ]
        if pending.empty:
            st.warning("没有同时满足模型概率≥52%且EV>0的候选。")
        else:
            size = st.selectbox("串关关数", [2, 3, 4, 5, 6, 7], index=2)
            max_groups = st.slider("显示组数", 3, 20, 8)
            mode = st.selectbox("组合模式", ["平衡模式", "优先命中率", "优先EV", "冷门高赔"])
            groups = []
            rows = pending.to_dict("records")
            for combo in combinations(rows, size):
                match_ids = [r.get("match_id") for r in combo]
                if len(match_ids) != len(set(match_ids)):
                    continue
                total_odds = math.prod(float(r["odds"]) for r in combo)
                joint_prob = math.prod(float(r["model_probability"]) / 100 for r in combo)
                avg_ev = sum(float(r["ev_percent"]) for r in combo) / size
                if mode == "优先命中率":
                    score = joint_prob
                elif mode == "优先EV":
                    score = avg_ev
                elif mode == "冷门高赔":
                    score = total_odds * max(joint_prob, 0.0001)
                else:
                    score = joint_prob * (1 + max(avg_ev, 0) / 100)
                groups.append((score, combo, total_odds, joint_prob, avg_ev))
            groups.sort(key=lambda x: x[0], reverse=True)
            for i, (_, combo, total_odds, joint_prob, avg_ev) in enumerate(groups[:max_groups], 1):
                legs = "<br>".join(
                    f"{r['market']}｜{r['selection']} @{float(r['odds']):.2f}"
                    for r in combo
                )
                st.markdown(
                    f"""<div class="quant-card">
                    <b>组合 {i}</b><br>{legs}<br><br>
                    总赔率：{total_odds:.2f}<br>
                    理论联合命中率：{joint_prob*100:.1f}%<br>
                    平均EV：{avg_ev:+.1f}%
                    </div>""",
                    unsafe_allow_html=True,
                )


elif page == "赛果结算":
    st.title("赛果结算")
    if bets_df.empty:
        st.info("暂无投注。")
    else:
        pending = bets_df[bets_df["result_status"] == "pending"].copy()
        if pending.empty:
            st.info("没有待结算投注。")
        else:
            pending["label"] = pending.apply(
                lambda r: f"{r['bet_date']}｜{r['market']}｜{r['selection']} @{r['odds']}",
                axis=1,
            )
            label = st.selectbox("选择投注", pending["label"].tolist())
            row = pending[pending["label"] == label].iloc[0]
            result_cn = st.selectbox("结果", ["全赢", "半赢", "走盘", "半输", "全输", "作废"])
            status_map = {
                "全赢": "full_win", "半赢": "half_win", "走盘": "push",
                "半输": "half_loss", "全输": "full_loss", "作废": "void",
            }
            status = status_map[result_cn]
            profit = settle_profit(status, float(row["stake"]), float(row["odds"]))
            st.metric("本单盈亏", f"RM {profit:+,.2f}")
            if st.button("确认结算"):
                try:
                    rest_patch(
                        "bets",
                        token,
                        {"id": f"eq.{row['id']}"},
                        {
                            "result_status": status,
                            "profit": profit,
                            "settled_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    clear_cache()
                    st.success("结算完成。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"结算失败：{exc}")


elif page == "赛后复盘":
    st.title("赛后复盘")
    if matches_df.empty:
        st.info("暂无赛事。")
    else:
        selectable = matches_df.copy()
        selectable["label"] = selectable.apply(
            lambda r: f"{r['match_date'].date()}｜{r['home_team']} vs {r['away_team']}",
            axis=1,
        )
        with st.form("review_form"):
            label = st.selectbox("比赛", selectable["label"].tolist())
            row = selectable[selectable["label"] == label].iloc[0]
            a, b = st.columns(2)
            with a:
                hs = st.number_input("主队射门", 0, 60, 10)
                hst = st.number_input("主队射正", 0, 30, 4)
                hp = st.number_input("主队控球%", 0.0, 100.0, 50.0)
                hc = st.number_input("主队角球", 0, 30, 4)
                hxg = st.number_input("主队xG", 0.0, 10.0, 1.20, 0.05)
            with b:
                aws = st.number_input("客队射门", 0, 60, 9)
                ast = st.number_input("客队射正", 0, 30, 3)
                ap = st.number_input("客队控球%", 0.0, 100.0, 50.0)
                ac = st.number_input("客队角球", 0, 30, 4)
                axg = st.number_input("客队xG", 0.0, 10.0, 1.00, 0.05)

            st.markdown("#### 进球来源")
            c1, c2 = st.columns(2)
            with c1:
                hop = st.number_input("主队运动战", 0, 10, 0)
                hsp = st.number_input("主队定位球", 0, 10, 0)
                hpen = st.number_input("主队点球", 0, 10, 0)
                howngoal = st.number_input("主队受益乌龙", 0, 10, 0)
            with c2:
                aop = st.number_input("客队运动战", 0, 10, 0)
                asp = st.number_input("客队定位球", 0, 10, 0)
                apen = st.number_input("客队点球", 0, 10, 0)
                aowngoal = st.number_input("客队受益乌龙", 0, 10, 0)

            game_flow = st.text_area("比赛走势与VAR")
            model_error = st.text_area("模型误差总结")
            adjustment = st.text_area("联赛参数调整")
            submit = st.form_submit_button("保存复盘")

        if submit:
            payload = {
                "user_id": user_id,
                "match_id": row["id"],
                "home_shots": hs, "away_shots": aws,
                "home_shots_on_target": hst, "away_shots_on_target": ast,
                "home_possession": hp, "away_possession": ap,
                "home_corners": hc, "away_corners": ac,
                "home_xg": hxg, "away_xg": axg,
                "home_open_play_goals": hop, "away_open_play_goals": aop,
                "home_set_piece_goals": hsp, "away_set_piece_goals": asp,
                "home_penalty_goals": hpen, "away_penalty_goals": apen,
                "home_own_goals": howngoal, "away_own_goals": aowngoal,
                "aos_actual": max(hop + hsp + hpen + howngoal, aop + asp + apen + aowngoal) >= 5,
                "game_flow": game_flow.strip() or None,
                "model_error_summary": model_error.strip() or None,
                "parameter_adjustment": adjustment.strip() or None,
            }
            try:
                existing = rest_get(
                    "match_reviews",
                    token,
                    {"select": "id", "match_id": f"eq.{row['id']}", "limit": "1"},
                )
                if existing:
                    rest_patch("match_reviews", token, {"id": f"eq.{existing[0]['id']}"}, payload)
                else:
                    rest_insert("match_reviews", token, payload)
                clear_cache()
                st.success("复盘已保存。")
            except Exception as exc:
                st.error(f"保存失败：{exc}")


elif page == "联赛模型":
    st.title("联赛模型")
    try:
        models = pd.DataFrame(load_models(token))
    except Exception as exc:
        st.error(str(exc))
        models = pd.DataFrame()

    if not models.empty:
        show = models[["league_code", "league_name", "model_version", "is_active", "notes"]]
        st.dataframe(show, use_container_width=True, hide_index=True)
    else:
        st.info("尚未建立联赛模型。")

    st.subheader("新增联赛模型")
    with st.form("league_model_form", clear_on_submit=True):
        code = st.text_input("联赛代码", placeholder="BRA_SERIE_A")
        name = st.text_input("联赛名称", placeholder="巴甲")
        notes = st.text_area("独立建模规则")
        submit = st.form_submit_button("保存模型")
    if submit:
        if not code.strip() or not name.strip():
            st.error("请填写代码与名称。")
        else:
            try:
                rest_insert("league_models", token, {
                    "user_id": user_id,
                    "league_code": code.strip().upper(),
                    "league_name": name.strip(),
                    "model_version": "V10",
                    "parameters": {},
                    "notes": notes.strip() or None,
                    "is_active": True,
                })
                clear_cache()
                st.success("联赛模型已保存。")
                st.rerun()
            except Exception as exc:
                st.error(f"保存失败：{exc}")


elif page == "报表中心":
    st.title("报表中心")
    if bets_df.empty:
        st.info("暂无投注数据。")
    else:
        settled_r = bets_df[bets_df["result_status"] != "pending"].copy()
        if settled_r.empty:
            st.info("暂无已结算投注。")
        else:
            summary = settled_r.groupby("strategy").agg(
                投注数=("id", "count"),
                总投注RM=("stake", "sum"),
                总盈亏RM=("profit", "sum"),
            ).reset_index()
            summary["ROI%"] = summary["总盈亏RM"] / summary["总投注RM"] * 100
            st.subheader("策略表现")
            st.dataframe(summary.round(2), use_container_width=True, hide_index=True)

            csv = bets_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("下载投注CSV", csv, "v10_bets.csv", "text/csv")


elif page == "系统设置":
    st.title("系统设置")
    st.write(f"账号：**{user.get('email', '')}**")
    st.write(f"用户ID：`{user_id}`")
    st.write("数据库：Supabase PostgreSQL")
    st.write("默认货币：MYR / RM")
    if bankroll:
        new_initial = st.number_input(
            "初始资金 RM",
            min_value=100.0,
            value=float(bankroll["initial_balance"]),
            step=100.0,
        )
        if st.button("更新初始资金"):
            try:
                rest_patch(
                    "bankrolls",
                    token,
                    {"id": f"eq.{bankroll['id']}"},
                    {"initial_balance": new_initial, "current_balance": new_initial},
                )
                clear_cache()
                st.success("资金已更新。")
                st.rerun()
            except Exception as exc:
                st.error(f"更新失败：{exc}")

    st.warning("当前V10为手动数据版。未接入已授权的赛事、首发、伤停或赔率API，不会自动抓取365Scores、UEFA或Maxbet。")
