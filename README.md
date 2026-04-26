# 投资雷达 (Investment Radar)

AI大模型赛道早期信号检测系统。

## Phase 0 — MVP (已完成)
- [x] GitHub Trending 采集 (真实 API)
- [x] arXiv 论文采集 (cs.AI/cs.CL)
- [x] Star 激增检测
- [x] LLM 丰富化 (MiniMax M2.7)
- [x] 微信推送 (stdout 格式)

## Phase 1 — 完整链路 (已完成)
- [x] **36kr 新闻采集** — RSS feed，AI/融资新闻检测
- [x] **HuggingFace Models** — API (需网络可达时可用)
- [x] **Star 历史追踪** — SQLite 存储，24h 对比
- [x] **关联分析** — Star激增 + 论文爆发 + 新闻 = 高置信度

## Phase 2 — 待开发
- [ ] 36kr 文章正文抓取
- [ ] HuggingFace 模型详情页抓取
- [ ] 每周报告生成 (LLM)
- [ ] 多赛道支持

## 快速开始

```bash
# 安装依赖
uv venv .venv
uv pip install -r requirements.txt

# 填写 API Key
cp .env.example .env
# 编辑 .env，填入 GITHUB_TOKEN 和 MINIMAX_API_KEY

# 运行 Pipeline
python scripts/run_local.py

# 运行测试
python scripts/run_local.py --skip-notification
```

## 数据源

| 数据源 | 类型 | 说明 |
|--------|------|------|
| GitHub Trending | API | 每日9:00采集 |
| arXiv cs.AI/cs.CL | API | 每日8:00/20:00 |
| 36kr 科技新闻 | RSS | 每日9:00/12:00/18:00 |
| HuggingFace | API | 每日10:00 (需网络) |

## 架构

```
scripts/run_local.py     # Pipeline 入口
src/采集/                # 数据采集 (GitHub/arXiv/36kr/HuggingFace)
src/检测/                # 信号检测 (Star/论文/新闻)
src/分析/                # LLM 丰富化
src/推送/                # 微信推送
src/core/                # 配置、数据库
config/tracks/           # 赛道配置 (AI/LLM)
```
