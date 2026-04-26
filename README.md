# 投资雷达 (Investment Radar)

> 面向人民币科技基金的 ToB 服务平台 — 实时追踪 AI/机器人/脑机接口等赛道的早期信号

## 产品定位

投资雷达从 GitHub Trending、arXiv 论文、HuggingFace 模型、36kr 新闻等多个数据源自动采集信号，通过变化检测算法识别异常增长，结合 LLM 生成投资解读，推送至微信/飞书/邮件。

## 项目状态

**Phase 0 开发中** — 本地 MVP 验证阶段

### 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| GitHub 数据采集 | ✅ | 真实 API，25 条 Trending |
| arXiv 论文采集 | ✅ | 限流处理，50 篇/次 |
| Star 变化检测 | ✅ | 环比异常，阈值可配 |
| 论文激增检测 | ✅ | 关键词过滤 |
| LLM 信号丰富化 | 🟡 | mock 模式，MiniMax 待接真实 API |
| 微信推送 | ✅ | stdout 输出，供 Hermes cron 捕获 |
| 端到端 Pipeline | ✅ | 1 条命令跑完整流程 |

## 快速开始

### 1. 克隆项目

```bash
cd /path/to/your/folder
# 或解压到现有目录
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate     # Windows
```

### 3. 安装依赖

```bash
.venv/bin/pip install loguru pyyaml requests beautifulsoup4 feedparser sqlalchemy apscheduler openai pydantic python-dotenv
```

> 注：如使用 uv：`uv venv .venv && uv pip install -r requirements.txt`

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入真实密钥
```

必须配置：
- `GITHUB_TOKEN` — [GitHub PAT](https://github.com/settings/tokens)（需勾选 `repo` scope）

可选配置：
- `MINIMAX_API_KEY` — LLM 丰富化（目前为 mock 模式）

### 5. 运行

```bash
# 完整流程（采集 → 检测 → 丰富 → 推送）
.venv/bin/python scripts/run_local.py

# 跳过推送（调试用）
.venv/bin/python scripts/run_local.py --skip-notification
```

### 6. 预期输出

```
========================================================
投资雷达 - Phase 0 MVP
========================================================
[1/4] 采集 GitHub Trending...
  成功: 25 条数据
[2/4] 采集 arXiv 论文...
  成功: 50 篇论文
[3/4] 信号检测...
  检测到 3 个告警
[4/4] LLM 丰富化...
  丰富化完成: 3 个信号
[推送] 微信通知...
  推送成功: 3 个信号
========================================================
结果: 采集✅ 检测✅ 丰富✅ 推送✅
```

微信消息格式：
```
📊 投资雷达 - 每日简报

🚨 [STAR_SURGE] owner/repo-name
  Star 1234，较之前增长 55%
  💡 含义: 🔥 owner/repo-name 增长迅猛...
```

## 项目结构

```
investment-radar/
├── config/
│   ├── settings.yaml         # 全局配置（数据库、调度、LLM）
│   └── tracks/
│       └── ai_llm.yaml      # AI大模型赛道配置
├── src/
│   ├── core/
│   │   ├── config.py        # 配置加载
│   │   └── database.py       # 数据库（Phase 1）
│   ├── 采集/
│   │   ├── base.py          # 采集器基类
│   │   ├── github.py        # GitHub 数据源
│   │   └── arxiv.py         # arXiv 数据源
│   ├── 检测/
│   │   ├── star_detector.py # Star 异常检测
│   │   └── paper_detector.py# 论文激增检测
│   ├── 分析/
│   │   └── enricher.py      # LLM 信号丰富化
│   └── 推送/
│       └── wechat.py        # 微信推送
├── scripts/
│   └── run_local.py         # 本地运行入口
├── data/                    # SQLite 数据库（Phase 1）
├── logs/                    # 日志目录
├── requirements.txt
├── .env                     # 环境变量（不上传 git）
└── .env.example             # 环境变量示例
```

## 开发规范

- **Shortcut 代码**：标注 `# 🚨 SHORTcut:` + `# TODO(FUTURE): [正确做法]`
- **Debug 代码**：标注 `# 🔧 DEBUG:`
- **周五死代码清理**，用户同意后才执行
- **Commit 检查清单**：Shortcut/Debug 标注 + 文档更新

详见 `开发规范.md`

## 赛道配置

目前支持 AI/LLM 赛道，其他赛道（机器人、脑机接口）Phase 2 扩展。

配置示例（`config/tracks/ai_llm.yaml`）：

```yaml
track_id: "ai_llm"
sources:
  - source_id: "github_trending"
    provider: "github"
    params:
      q: "language:python created:>{date_7d}"
      sort: "stars"
detection_rules:
  - rule_id: "star_surge"
    threshold:
      high: 0.5   # 50% 增长 → 高优先级
      medium: 0.3
```

## 后续计划

| 阶段 | 时间 | 目标 |
|------|------|------|
| Phase 1 | 第2-3周 | AI大模型赛道完整验证 |
| Phase 2 | 第4-6周 | 机器人 + 脑机接口赛道 |
| Phase 3 | 第7-8周 | 多租户平台化 |

详见 `实施路线图.md`

## 技术栈

- **语言**: Python 3.11+
- **数据采集**: requests, feedparser, BeautifulSoup
- **数据库**: SQLite（开发）→ PostgreSQL/TimescaleDB（生产）
- **LLM**: OpenAI 兼容接口（MiniMax/GPT-4o/Claude）
- **调度**: APScheduler（开发）→ Airflow/K8s CronJob（生产）
- **推送**: 微信（Hermes）、飞书、邮件
