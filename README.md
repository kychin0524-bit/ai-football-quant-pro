# AI Football Quant Pro

手机和电脑都能访问的足球量化投注记录与分析系统。

## 已完成功能

- RM 马币资金管理
- 手机响应式 Dashboard
- 新增投注
- 全赢、半赢、走盘、半输、全输结算
- 自动计算盈亏、ROI、最大回撤、命中率
- 资金曲线与每日盈亏
- 正常、冷门、平局、平衡、上半场、大小球、让球、串关策略分类
- 联赛独立统计
- SQLite 本地数据库
- EV 与 Kelly 提示

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

浏览器打开终端显示的网址。

## 手机在线部署：Streamlit Community Cloud

1. 注册 GitHub。
2. 新建仓库并上传本项目所有文件。
3. 登录 Streamlit Community Cloud。
4. 选择仓库、分支以及 `app.py`。
5. 点击 Deploy。
6. 部署完成后会获得一个网址，iPhone 和 Android 都能打开。

## 重要说明

当前版本是记录、结算、统计和资金管理 MVP。
它不会自动抓取 Maxbet、365Scores 或 UEFA 数据。
接入第三方数据前，需要确认接口授权、使用条款及当地法规。

## 下一版计划

- 2串1至7串1逐腿结算
- Excel/CSV导入导出
- 登录与云数据库 PostgreSQL
- CLV记录
- 模型版本管理
- 赛前分析与赛后复盘模块
- AOS与进球来源标签
