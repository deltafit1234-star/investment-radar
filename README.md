# 投资雷达 (Investment Radar) — Phase 3 多租户版

AI大模型赛道早期信号检测系统，支持多租户、多赛道、微信/飞书/邮件分群推送。

## 项目阶段

| Phase | 状态 | 内容 |
|-------|------|------|
| Phase 0 | ✅ 已完成 | 本地最小闭环（GitHub/arXiv/微信推送） |
| Phase 1 | ✅ 已完成 | 单赛道验证（36kr/HuggingFace/Star历史追踪） |
| Phase 2 | ✅ 已完成 | 多赛道扩展（人形机器人/自动驾驶/半导体/BCI/新能源） |
| Phase 3 | ✅ 已完成 | 多租户平台化（数据库/配置/Pipeline/API/Web管理后台） |
| Phase 4 | 🔄 进行中 | Premium 深度分析高级服务（二期待上线） |

## 赛道清单

| 赛道 ID | 名称 | 数据源 |
|---------|------|--------|
| `ai_llm` | AI 大模型 | GitHub Trending + arXiv cs.AI/cs.CL + 36kr |
| `humanoid_robot` | 人形机器人 | GitHub Trending + arXiv cs.RO + 36kr |
| `autonomous_driving` | 自动驾驶 | GitHub Trending + arXiv cs.AI/cs.RO + 36kr |
| `semiconductor` | 半导体 | GitHub Trending + arXiv physics.app-ph + 36kr |
| `bci` | 脑机接口 | GitHub Trending + arXiv cs.NE/q-bio.QM + 36kr |
| `new_energy` | 新能源 | GitHub Trending + arXiv physics.app-ph + 36kr |

## 快速开始

```bash
# 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置 API Keys（必填 GITHUB_TOKEN + MINIMAX_API_KEY）
cp .env.example .env  # 或手动创建 .env

# 运行采集 Pipeline
python scripts/run_local.py

# 启动 Web Dashboard + API
python scripts/app.py --port 8765
# 访问 http://localhost:8765/
```

## 文档目录

| 文件 | 说明 |
|------|------|
| `INSTALL.md` | 安装部署指南 |
| `API.md` | REST API + WebSocket 接口文档 |
| `多租户系统架构设计.md` | 多租户架构设计文档 |
| `实施路线图.md` | 完整开发路线图 |
| `开发规范.md` | Shortcut/Debug 代码规范 |
| `赛道清单与数据源分析.md` | 各赛道数据源详细说明 |

## 核心架构

```
scripts/run_local.py     # Pipeline 入口（采集→检测→丰富→存库→推送）
scripts/app.py          # Dashboard + REST API（FastAPI）
src/
├── 采集/                 # 数据采集（GitHub/arXiv/36kr/HuggingFace）
├── 检测/                 # 信号检测（Star激增/论文爆发/新闻）
├── 分析/
│   ├── enricher.py      # 标准 LLM 丰富化（所有信号）
│   └── deep_analyzer.py # Premium 深度分析（Phase 4）
├── 推送/
│   ├── wechat.py       # 微信推送（已实现）
│   ├── feishu.py       # 飞书推送（预留）
│   ├── email.py        # 邮件推送（预留）
│   └── router.py       # 多租户推送路由器
├── api/
│   └── tenant_routes.py # 多租户 REST API（13条路由）
└── core/
    ├── config.py        # 全局配置加载
    ├── database.py      # 数据库 ORM（SQLite）
    ├── track_loader.py  # 赛道配置加载
    └── tenant_config.py # 多租户关键词合并
```

## 数据分层（Premium 服务）

```
Signal.tenant_ids       # 订阅该信号的租户列表
Signal.analysis_premium # Premium 深度分析（Premium 租户可见）
Signal.ad_space         # 广告位（Basic 租户可见，引导升级）
Signal.has_premium_content # 是否有 Premium 内容
```

## 多租户推送路由

```
信号产生 → NotificationRouter.route_signals()
           → 读取 Signal.tenant_ids
           → 查询 TenantSubscription（按 plan 过滤）
           → 按租户渠道配置分群推送（微信/飞书/邮件）
           → 记录 Alert 到数据库
```
