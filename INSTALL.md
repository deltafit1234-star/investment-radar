# 投资雷达 — 安装部署指南

> 适用版本：Phase 3 多租户版
> Python 版本：3.11+

---

## 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.11+ |
| 操作系统 | Linux / macOS / WSL2 |
| 网络 | 可访问 GitHub / arXiv / 36kr |
| 微信推送 | Hermes Bridge（ilinkai 云服务） |
| 磁盘 | ≥ 1GB（SQLite 数据库 + 日志） |

---

## 一、快速安装

### 1. 创建虚拟环境

```bash
cd investment-radar/
python3 -m venv .venv
source .venv/bin/activate      # Linux/macOS/WSL2
# .venv\Scripts\activate       # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env           # 如果存在 .env.example
# 或者手动创建 .env
```

`.env` 文件内容：

```env
# ── 数据源 API Keys ───────────────────────────────
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
# 申请地址：https://github.com/settings/tokens（需要 repo 权限）

MINIMAX_API_KEY=eyJhbGciOiJxxx
# MiniMax API Key（用于 LLM 丰富化和深度分析）
# 申请地址：https://platform.minimax.io/

# ── 微信推送（Hermes Bridge）──────────────────────
HERMES_BRIDGE_TOKEN=your_hermes_bridge_token_here
# 联系系统管理员获取

# ── 采集配置 ─────────────────────────────────────
ARXIV_API_KEY=                # arXiv 无需 Key（有 429 限流）
# HF_TOKEN=                   # HuggingFace（可选，cron 环境 443 不通可留空）
```

### 4. 验证安装

```bash
# 检查 Python 版本和依赖
python --version              # 应显示 3.11+
.venv/bin/python -c "import requests, yaml, loguru; print('依赖正常')"
```

---

## 二、目录结构

```
investment-radar/
├── config/                    # 赛道配置文件
│   ├── settings.yaml          # 全局配置
│   └── tracks/                # 各赛道独立配置
│       ├── ai_llm.yaml
│       ├── humanoid_robot.yaml
│       ├── autonomous_driving.yaml
│       ├── semiconductor.yaml
│       ├── bci.yaml
│       └── new_energy.yaml
├── data/                      # SQLite 数据库（自动创建）
│   └── radar.db
├── logs/                      # 日志文件
├── scripts/
│   ├── run_local.py           # 🚀 Pipeline 入口
│   ├── app.py                 # 🌐 Dashboard + API 服务
│   └── *.py                   # 工具脚本
├── src/
│   ├── 采集/                   # 数据采集器
│   ├── 检测/                   # 信号检测逻辑
│   ├── 分析/                   # LLM 丰富化 + 深度分析
│   │   ├── enricher.py         # 标准丰富化（所有信号）
│   │   └── deep_analyzer.py    # Premium 深度分析
│   ├── 推送/                   # 推送渠道
│   │   ├── wechat.py           # 微信（已实现）
│   │   ├── feishu.py           # 飞书（预留）
│   │   ├── email.py            # 邮件（预留）
│   │   └── router.py           # 多租户推送路由器
│   ├── api/
│   │   └── tenant_routes.py    # 多租户 REST API
│   └── core/
│       ├── config.py          # 配置加载
│       ├── database.py         # 数据库 ORM + CRUD
│       ├── track_loader.py     # 赛道配置加载
│       └── tenant_config.py    # 多租户配置合并
├── requirements.txt
├── .env                       # API Keys（不提交到 Git）
├── 多租户系统架构设计.md        # 架构文档
├── 实施路线图.md               # 开发路线图
├── 开发规范.md                 # 开发规范
└── 赛道清单与数据源分析.md     # 数据源清单
```

---

## 三、运行方式

### 3.1 采集 Pipeline（定时任务）

```bash
# 激活虚拟环境
source .venv/bin/activate

# 全赛道采集（cron 方式，推荐每日 1-2 次）
python scripts/run_local.py

# 单赛道采集（调试用）
python scripts/run_local.py --track bci

# 跳过推送（仅采集+存库）
python scripts/run_local.py --skip-notification

# 采集后推送到指定群（微信 chat_id）
python scripts/run_local.py --track ai_llm --deliver-to "weixin:chat_id_here"

# 生成周报
python scripts/run_local.py --mode weekly
```

### 3.2 Web Dashboard + API

```bash
# 启动服务
python scripts/app.py --port 8765

# 生产模式（监听所有网卡）
python scripts/app.py --host 0.0.0.0 --port 8765

# 开发模式（代码变更自动重载）
python scripts/app.py --port 8765 --reload
```

启动后访问：**http://localhost:8765/**

### 3.3 定时调度（Linux Crontab）

```bash
# 编辑 crontab
crontab -e

# 每日 9:00 采集全赛道（周一到周五）
0 9 * * 1-5 cd /path/to/investment-radar && .venv/bin/python scripts/run_local.py >> logs/cron.log 2>&1

# 每周五 18:00 生成周报
0 18 * * 5 cd /path/to/investment-radar && .venv/bin/python scripts/run_local.py --mode weekly >> logs/weekly.log 2>&1
```

---

## 四、Docker 部署（可选）

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "scripts/app.py", "--host", "0.0.0.0", "--port", "8765"]
```

```bash
# 构建
docker build -t investment-radar:latest .

# 运行
docker run -d -p 8765:8765 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --env-file .env \
  investment-radar:latest
```

---

## 五、微信推送配置

微信推送通过 Hermes Bridge（ilinkai 云服务）实现。首次配置：

1. 在微信中联系 ilinkai 服务号，获取 `HERMES_BRIDGE_TOKEN`
2. 将 token 填入 `.env`
3. 把 Hermes bot 拉入目标群聊
4. 群聊 chat_id 填入租户推送配置或 `--deliver-to` 参数

---

## 六、多租户配置（管理后台）

Dashboard「🏢 多租户」Tab 提供：

- **创建租户**：ID + 名称 + Plan（basic/premium）
- **订阅赛道**：租户订阅哪些赛道 + sensitivity 阈值
- **推送配置**：微信 target / 邮件地址
- **Webhook 回调**：天翼云订阅变更回调接口

---

## 七、常见问题

**Q: arXiv 返回 429 限流？**
> 系统自动降级为 RSS 模式，不影响功能。

**Q: MiniMax API Key 未配置？**
> LLM 丰富化降级为 mock 模式，信号仍可正常采集和推送，仅无 LLM 摘要。

**Q: 数据库报错 no such table？**
> 运行一次 `python scripts/run_local.py`，会自动初始化数据库表。

**Q: HuggingFace 采集失败？**
> cron 环境 443 端口不通属正常现象，系统自动跳过 HF 数据源，不影响其他采集。

**Q: Dashboard 端口被占用？**
> `lsof -ti:8765 | xargs kill -9` 释放端口后重试。
