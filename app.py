import sqlite3
from datetime import date, datetime
from pathlib import Path
import io
import math

import pandas as pd
import streamlit as st

APP_NAME = "AI Football Quant Pro V2"
DB_PATH = Path("football_quant_v2.db")

st.set_page_config(
    page_title=APP_NAME,
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(""" <style> .block-container {padding-top: .8rem; padding-bottom: 5rem; max-width: 1180px;} [data-testid="stMetric"]{ background:#101823;border:1px solid #24496e;border-radius:18px;padding:16px; } [data-testid="stMetricValue"]{font-size:1.65rem;} .stButton>button{width:100%;border-radius:12px;min-height:44px;font-weight:700;} div[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden;} .small-note{font-size:.88rem;color:#9ca3af;} .card{background:#101823;border:1px solid #24496e;border-radius:18px;padding:16px;margin-bottom:12px;} @media(max-width:768px){ .block-container{padding-left:.7rem;padding-right:.7rem;} [data-testid="column"]{min-width:100%!important;flex:1 1 100%!important;} [data-testid="stMetricValue"]{font-size:1.4rem;} } </style> """, unsafe_allow_html=True)

def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute(""" CREATE TABLE IF NOT EXISTS bets( id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, match_date TEXT NOT NULL, league TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL, market TEXT NOT NULL, selection TEXT NOT NULL, line REAL, odds REAL NOT NULL, stake REAL NOT NULL, strategy TEXT NOT NULL, model_probability REAL, result_status TEXT NOT NULL DEFAULT '未结算', profit REAL NOT NULL DEFAULT 0, notes TEXT )""")
    cur.execute(""" CREATE TABLE IF NOT EXISTS bankroll( id INTEGER PRIMARY KEY CHECK(id=1), initial_balance REAL NOT NULL )""")
    cur.execute("INSERT OR IGNORE INTO bankroll(id,initial_balance) VALUES(1,10000)")
    cur.execute(""" CREATE TABLE IF NOT EXISTS parlays( id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, parlay_date TEXT NOT NULL, name TEXT NOT NULL, legs TEXT NOT NULL, total_odds REAL NOT NULL, stake REAL NOT NULL, result_status TEXT NOT NULL DEFAULT '未结算', profit REAL NOT NULL DEFAULT 0 )""")
    c.commit(); c.close()

def qdf(query, params=()):
    c=conn()
    df=pd.read_sql_query(query,c,params=params)
    c.close()
    return df

def execq(query, params=()):
    c=conn(); cur=c.cursor(); cur.execute(query,params); c.commit(); c.close()

def settle_profit(status, stake, odds):
    return round({
        "全赢": stake*(odds-1),
        "半赢": stake*(odds-1)/2,
        "走盘": 0,
        "半输": -stake/2,
        "全输": -stake,
        "未结算": 0,
    }[status],2)

def kelly_fraction(probability, odds):
    if odds<=1: return 0
    p=probability/100
    b=odds-1
    return max(0, (b*p-(1-p))/b)

def max_drawdown(eq):
    if eq.empty: return 0.0
    peak=eq.cummax()
    dd=(eq-peak)/peak.replace(0,pd.NA)
    return float(dd.min()*100) if len(dd) else 0.0

def summarize(group):
    if group.empty:
        return pd.Series({"投注数":0,"等效命中":0,"命中率%":0,"总投注RM":0,"总盈亏RM":0,"ROI%":0})
    wins=group["result_status"].map({"全赢":1,"半赢":0.5,"走盘":0,"半输":0,"全输":0}).sum()
    stake=group["stake"].sum()
    profit=group["profit"].sum()
    return pd.Series({
        "投注数":len(group),"等效命中":wins,
        "命中率%":wins/len(group)*100,
        "总投注RM":stake,"总盈亏RM":profit,
        "ROI%":profit/stake*100 if stake else 0
    })

init_db()

with st.sidebar:
    st.title("⚽ Quant Pro V2")
    page=st.radio("导航",[
        "首页仪表盘","今日推荐","新增投注","赛果结算",
        "串关中心","投注记录","策略分析","数据导入导出","资金设置"
    ],label_visibility="collapsed")
    st.caption("默认货币：RM 马币")

bets=qdf("SELECT * FROM bets ORDER BY match_date,id")
initial=float(qdf("SELECT initial_balance FROM bankroll WHERE id=1").iloc[0,0])

if not bets.empty:
    bets["match_date"]=pd.to_datetime(bets["match_date"])
    bets["created_at"]=pd.to_datetime(bets["created_at"])
    for c in ["profit","stake","odds","model_probability"]:
        bets[c]=pd.to_numeric(bets[c],errors="coerce")
    settled=bets[bets["result_status"]!="未结算"].copy()
else:
    settled=pd.DataFrame()

current=initial+(settled["profit"].sum() if not settled.empty else 0)
roi=(current/initial-1)*100 if initial else 0

if page=="首页仪表盘":
    st.title("AI Football Quant Pro V2")
    st.caption("数据驱动 · 概率建模 · 风险控制 · 联赛独立统计")

    if not settled.empty:
        settled=settled.sort_values(["match_date","id"])
        settled["equity"]=initial+settled["profit"].cumsum()
        hit=settled["result_status"].map({"全赢":1,"半赢":0.5,"走盘":0,"半输":0,"全输":0}).sum()/len(settled)*100
        mdd=max_drawdown(settled["equity"])
        daily=settled.groupby(settled["match_date"].dt.date)["profit"].sum()
        prof_days=(daily>0).mean()*100 if len(daily) else 0
    else:
        hit=mdd=prof_days=0

    c1,c2,c3,c4=st.columns(4)
    c1.metric("当前资金",f"RM {current:,.2f}",f"{roi:+.1f}%")
    c2.metric("综合命中率",f"{hit:.1f}%")
    c3.metric("最大回撤",f"{mdd:.1f}%")
    c4.metric("盈利天数占比",f"{prof_days:.1f}%")

    st.subheader("资金增长曲线")
    if not settled.empty:
        st.line_chart(settled.set_index("match_date")[["equity"]],height=320)
    else:
        st.info("暂无已结算投注。")

    st.subheader("每日盈亏")
    if not settled.empty:
        st.bar_chart(daily.to_frame(),height=280)

    st.subheader("最近10笔")
    if not bets.empty:
        r=bets.sort_values("created_at",ascending=False).head(10).copy()
        r["比赛"]=r["home_team"]+" vs "+r["away_team"]
        show=r[["match_date","league","比赛","market","selection","odds","stake","result_status","profit"]]
        show.columns=["日期","联赛","比赛","市场","选择","赔率","注额RM","结果","盈亏RM"]
        st.dataframe(show,use_container_width=True,hide_index=True)
    else: st.info("暂无记录。")

elif page=="今日推荐":
    st.title("今日推荐")
    st.caption("这是人工录入与量化筛选页面；当前版本不会自动抓取赛事。")
    today=bets[bets["match_date"].dt.date==date.today()] if not bets.empty else pd.DataFrame()
    if today.empty:
        st.info("今天还没有录入赛事。到“新增投注”先录入。")
    else:
        today=today.copy()
        today["隐含概率%"]=100/today["odds"]
        today["EV%"]=today["model_probability"]/100*today["odds"]*100-100
        today["1/4 Kelly%"]=today.apply(lambda r:kelly_fraction(r["model_probability"],r["odds"])*25,axis=1)
        today["比赛"]=today["home_team"]+" vs "+today["away_team"]
        today["评级"]=pd.cut(today["EV%"],[-999,0,5,10,999],labels=["放弃","观察","推荐","强推荐"])
        show=today[["league","比赛","market","selection","odds","model_probability","隐含概率%","EV%","1/4 Kelly%","评级"]]
        show.columns=["联赛","比赛","市场","选择","赔率","模型概率%","隐含概率%","EV%","建议注额%","评级"]
        st.dataframe(show.round(2),use_container_width=True,hide_index=True)

elif page=="新增投注":
    st.title("新增投注")
    with st.form("add",clear_on_submit=True):
        a,b=st.columns(2)
        with a:
            md=st.date_input("比赛日期",date.today())
            league=st.text_input("联赛/杯赛")
            home=st.text_input("主队")
            away=st.text_input("客队")
            market=st.selectbox("市场",["亚洲让球","全场大小","上半场大小","独赢","平局","双重机会","比分","串关"])
        with b:
            selection=st.text_input("选择",placeholder="例如：小3.0、客队+1")
            line=st.number_input("盘口线",value=0.0,step=0.25)
            odds=st.number_input("赔率",min_value=1.01,value=1.90,step=.01)
            stake=st.number_input("注额 RM",min_value=1.0,value=100.0,step=10.0)
            strategy=st.selectbox("策略",["正常策略","冷门策略","平局策略","平衡策略","上半场策略","大小球策略","让球策略","串关策略"])
        prob=st.slider("模型概率%",0.0,100.0,55.0,.5)
        implied=100/odds
        ev=prob/100*odds-1
        k=kelly_fraction(prob,odds)
        st.info(f"隐含概率 {implied:.1f}%｜EV {ev*100:+.1f}%｜1/4 Kelly {k*25:.1f}%")
        notes=st.text_area("备注")
        ok=st.form_submit_button("保存投注")
        if ok:
            if not all([league.strip(),home.strip(),away.strip(),selection.strip()]):
                st.error("请填完整联赛、主队、客队和选择。")
            else:
                execq("""INSERT INTO bets(created_at,match_date,league,home_team,away_team,market,selection,line,odds,stake,strategy,model_probability,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                    datetime.now().isoformat(timespec="seconds"),md.isoformat(),league.strip(),home.strip(),away.strip(),market,
                    selection.strip(),line,odds,stake,strategy,prob,notes.strip()))
                st.success("已保存。")

elif page=="赛果结算":
    st.title("赛果结算")
    pending=qdf("SELECT * FROM bets WHERE result_status='未结算' ORDER BY match_date,id")
    if pending.empty: st.info("没有待结算记录。")
    else:
        pending["label"]=pending.apply(lambda r:f"#{r['id']}｜{r['match_date']}｜{r['home_team']} vs {r['away_team']}｜{r['selection']} @{r['odds']}",axis=1)
        lab=st.selectbox("选择投注",pending["label"])
        row=pending[pending["label"]==lab].iloc[0]
        status=st.selectbox("结果",["全赢","半赢","走盘","半输","全输"])
        profit=settle_profit(status,float(row["stake"]),float(row["odds"]))
        st.metric("本单盈亏",f"RM {profit:+,.2f}")
        if st.button("确认结算"):
            execq("UPDATE bets SET result_status=?,profit=? WHERE id=?",(status,profit,int(row["id"])))
            st.success("结算完成。")

elif page=="串关中心":
    st.title("串关中心")
    st.caption("当前版本支持整张串关票记录与结算。")
    tab1,tab2=st.tabs(["新增串关","结算串关"])
    with tab1:
        with st.form("parlay_add",clear_on_submit=True):
            pdte=st.date_input("串关日期",date.today(),key="pdte")
            name=st.text_input("串关名称",placeholder="例如：欧冠+巴甲 4串1")
            legs=st.text_area("串关内容",placeholder="每行一关，例如：费内巴切 小3.0 @1.88")
            total_odds=st.number_input("总赔率",min_value=1.01,value=5.00,step=.01)
            stake=st.number_input("注额 RM",min_value=1.0,value=20.0,step=10.0,key="pstake")
            if st.form_submit_button("保存串关"):
                if not name.strip() or not legs.strip():
                    st.error("请填写名称和串关内容。")
                else:
                    execq("INSERT INTO parlays(created_at,parlay_date,name,legs,total_odds,stake) VALUES(?,?,?,?,?,?)",
                          (datetime.now().isoformat(timespec="seconds"),pdte.isoformat(),name.strip(),legs.strip(),total_odds,stake))
                    st.success("串关已保存。")
    with tab2:
        p=qdf("SELECT * FROM parlays WHERE result_status='未结算' ORDER BY parlay_date,id")
        if p.empty: st.info("没有待结算串关。")
        else:
            p["label"]=p.apply(lambda r:f"#{r['id']}｜{r['parlay_date']}｜{r['name']}｜@{r['total_odds']}",axis=1)
            lab=st.selectbox("选择串关",p["label"],key="parlay_select")
            row=p[p["label"]==lab].iloc[0]
            st.code(row["legs"])
            status=st.selectbox("串关结果",["全赢","走盘","全输"])
            profit=settle_profit(status,float(row["stake"]),float(row["total_odds"]))
            st.metric("串关盈亏",f"RM {profit:+,.2f}")
            if st.button("确认串关结算"):
                execq("UPDATE parlays SET result_status=?,profit=? WHERE id=?",(status,profit,int(row["id"])))
                st.success("串关结算完成。")

elif page=="投注记录":
    st.title("投注记录")
    if bets.empty: st.info("暂无记录。")
    else:
        d=bets.copy(); d["比赛"]=d["home_team"]+" vs "+d["away_team"]
        show=d[["id","match_date","league","比赛","market","selection","line","odds","stake","strategy","model_probability","result_status","profit","notes"]]
        show.columns=["ID","日期","联赛","比赛","市场","选择","盘口","赔率","注额RM","策略","模型概率%","结果","盈亏RM","备注"]
        st.dataframe(show.sort_values(["日期","ID"],ascending=False),use_container_width=True,hide_index=True)
        did=st.number_input("删除ID",min_value=0,step=1)
        if st.button("删除记录"):
            if did>0:
                execq("DELETE FROM bets WHERE id=?",(int(did),))
                st.success("已删除。")

elif page=="策略分析":
    st.title("策略分析")
    if settled.empty: st.info("需要先结算投注。")
    else:
        bys=settled.groupby("strategy").apply(summarize).reset_index()
        byl=settled.groupby("league").apply(summarize).reset_index()
        st.subheader("策略矩阵")
        st.dataframe(bys.round(2),use_container_width=True,hide_index=True)
        st.subheader("联赛独立统计")
        st.dataframe(byl.round(2),use_container_width=True,hide_index=True)

elif page=="数据导入导出":
    st.title("数据导入导出")
    st.subheader("导出")
    if not bets.empty:
        csv=bets.to_csv(index=False).encode("utf-8-sig")
        st.download_button("下载全部投注 CSV",csv,"football_bets.csv","text/csv")
    else: st.info("暂无数据可导出。")
    st.subheader("导入")
    up=st.file_uploader("上传CSV",type=["csv"])
    if up is not None:
        df=pd.read_csv(up)
        needed=["match_date","league","home_team","away_team","market","selection","odds","stake","strategy"]
        missing=[c for c in needed if c not in df.columns]
        if missing:
            st.error("缺少字段："+", ".join(missing))
        else:
            st.dataframe(df.head(),use_container_width=True)
            if st.button("确认导入"):
                for _,r in df.iterrows():
                    execq("""INSERT INTO bets(created_at,match_date,league,home_team,away_team,market,selection,line,odds,stake,strategy,model_probability,result_status,profit,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                        datetime.now().isoformat(timespec="seconds"),str(r["match_date"]),str(r["league"]),str(r["home_team"]),str(r["away_team"]),
                        str(r["market"]),str(r["selection"]),float(r.get("line",0) or 0),float(r["odds"]),float(r["stake"]),str(r["strategy"]),
                        float(r.get("model_probability",0) or 0),str(r.get("result_status","未结算")),float(r.get("profit",0) or 0),str(r.get("notes",""))))
                st.success(f"已导入 {len(df)} 条。")

elif page=="资金设置":
    st.title("资金设置")
    st.metric("当前初始资金",f"RM {initial:,.2f}")
    nb=st.number_input("设置初始资金 RM",min_value=100.0,value=float(initial),step=100.0)
    if st.button("保存"):
        execq("UPDATE bankroll SET initial_balance=? WHERE id=1",(nb,))
        st.success("已更新。")
    st.subheader("建议风控")
    st.write(""" - 单注：本金1%–3% - 高EV策略：最多1/4  Kelly - 每日止损：本金5%–8% - 单关与串关分开统计 - 各联赛独立查看ROI """)
