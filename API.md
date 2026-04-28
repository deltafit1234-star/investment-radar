# 投资雷达 — API 接口文档

> 适用版本：Phase 3 多租户版
> Base URL：`http://localhost:8765`
> 认证：无（内网部署，天翼云回调通过约定密钥验证）

---

## 一、REST API

### 1.1 租户管理

#### 创建租户

```
POST /api/v1/tenants
Content-Type: application/json

{
  "id": "fund_001",
  "name": "测试基金",
  "plan": "basic"
}

Response 200:
{
  "id": "fund_001",
  "name": "测试基金",
  "plan": "basic",
  "is_active": true,
  "created_at": "2026-04-28T12:00:00"
}
```

#### 列出所有租户

```
GET /api/v1/tenants

Response 200:
[
  {"id": "fund_001", "name": "测试基金", "plan": "basic", ...},
  {"id": "fund_002", "name": "高级基金", "plan": "premium", ...}
]
```

#### 获取租户详情

```
GET /api/v1/tenants/{tenant_id}

Response 200:
{
  "id": "fund_001",
  "name": "测试基金",
  "plan": "basic",
  "is_active": true,
  "created_at": "2026-04-28T12:00:00"
}
```

#### 更新租户

```
PUT /api/v1/tenants/{tenant_id}
Content-Type: application/json

{
  "name": "新名称",
  "plan": "premium"
}

Response 200: 返回更新后的租户对象
```

#### 停用租户（软删除）

```
DELETE /api/v1/tenants/{tenant_id}

Response 200:
{"ok": true, "message": "租户 fund_001 已停用"}
```

---

### 1.2 订阅管理

#### 获取租户的订阅列表

```
GET /api/v1/tenants/{tenant_id}/subscriptions

Response 200:
[
  {
    "id": 1,
    "tenant_id": "fund_001",
    "track_id": "bci",
    "sensitivity": "high",
    "keywords_append": ["脑机接口"],
    "keywords_exclude": [],
    "plan": "basic",
    "enabled": true,
    "created_at": "2026-04-28T12:00:00"
  }
]
```

#### 批量更新订阅（幂等）

```
PUT /api/v1/tenants/{tenant_id}/subscriptions
Content-Type: application/json

{
  "subscriptions": [
    {
      "track_id": "bci",
      "sensitivity": "high",
      "keywords_append": ["脑机接口", "neural interface"],
      "keywords_exclude": [],
      "plan": "basic",
      "enabled": true
    },
    {
      "track_id": "new_energy",
      "sensitivity": "medium",
      "keywords_append": ["储能"],
      "plan": "premium",
      "enabled": true
    }
  ]
}

Response 200:
{
  "subscriptions": [
    {"id": 3, "tenant_id": "fund_001", "track_id": "bci", ...},
    {"id": 4, "tenant_id": "fund_001", "track_id": "new_energy", ...}
  ]
}
```

> **注意**：`keywords_append` 是追加模式，只能添加系统级关键词，不能覆盖或删除。

#### 取消订阅某个赛道

```
DELETE /api/v1/tenants/{tenant_id}/subscriptions/{track_id}

Response 200:
{"ok": true}
```

---

### 1.3 推送配置

#### 获取推送配置

```
GET /api/v1/tenants/{tenant_id}/notification

Response 200:
{
  "tenant_id": "fund_001",
  "wechat_target": "o9cq801xxx@im.wechat",
  "feishu_webhook": null,
  "email": null,
  "daily_brief_time": "08:30",
  "real_time_alert_enabled": true,
  "real_time_threshold": "medium",
  "weekly_report_enabled": false,
  "weekly_report_day": "monday"
}
```

#### 更新推送配置

```
PUT /api/v1/tenants/{tenant_id}/notification
Content-Type: application/json

{
  "wechat_target": "o9cq801xxx@im.wechat",
  "email": "alert@fund.com",
  "daily_brief_time": "08:30",
  "real_time_alert_enabled": true,
  "real_time_threshold": "high",
  "weekly_report_enabled": true,
  "weekly_report_day": "friday"
}

Response 200: 返回更新后的配置对象
```

---

### 1.4 信号查询

#### 获取信号列表（按租户过滤）

```
GET /api/v1/signals?tenant_id={tenant_id}&plan={plan}&track_id={track_id}&limit={limit}&offset={offset}

Query Parameters:
  - tenant_id    必填：租户ID
  - plan         可选：basic / premium（默认 basic）
                 basic    → 返回 ad_space 广告位
                 premium  → 返回 analysis_premium 深度分析
  - track_id     可选：过滤赛道
  - priority     可选：high / medium / low
  - limit        可选：最大返回条数（默认 50，最大 200）
  - offset       可选：分页偏移

Response 200:
{
  "data": [
    {
      "id": 71,
      "track_id": "bci",
      "source_id": "paper_burst",
      "signal_type": "paper_burst",
      "title": "...",
      "content": "...",
      "priority": "high",
      "meaning": "...",
      "tenant_ids": ["fund_001"],
      "is_read": false,
      "has_premium_content": true,
      "analysis_premium": "【深度分析 · Premium】...",   # plan=premium 时返回
      "ad_space": "...",                                  # plan=basic 时返回
      "created_at": "2026-04-28T07:29:41"
    }
  ],
  "tenant_id": "fund_001",
  "plan": "premium",
  "count": 1
}
```

> **信号内容分层逻辑**：
> - `plan=basic`：返回 `ad_space`（引导升级 Premium）
> - `plan=premium`：返回 `analysis_premium`（深度分析内容）
> - `has_premium_content=false`：该信号从未被 Premium 订阅过

---

### 1.5 赛道管理

#### 列出所有赛道

```
GET /api/v1/tracks

Response 200:
[
  {
    "track_id": "ai_llm",
    "track_name": "AI大模型",
    "category": "AI",
    "enabled": true,
    "description": "..."
  },
  {
    "track_id": "bci",
    "track_name": "脑机接口",
    "category": "前沿技术",
    "enabled": true,
    "description": "..."
  }
]
```

---

### 1.6 天翼云订阅回调

#### 订阅变更回调

```
POST /api/v1/internal/webhooks/subscription
Content-Type: application/json

{
  "tenant_id": "tianyi_fund_001",
  "tenant_name": "天翼测试基金",
  "plan": "premium",
  "subscriptions": [
    {
      "track_id": "semiconductor",
      "sensitivity": "high",
      "keywords_append": ["国产替代"],
      "keywords_exclude": [],
      "plan": "premium",
      "enabled": true
    }
  ],
  "notification": {
    "wechat_target": "wechat_chat_abc",
    "email": "alert@tianyifund.com"
  }
}

Response 200:
{"ok": true, "tenant_id": "tianyi_fund_001"}
```

> **用途**：天翼云平台订阅变更后，调用此接口通知投资雷达更新租户配置。
> 幂等设计：重复调用会覆盖已有配置。

---

## 二、内部 API（非公开）

### 推送统计

```
GET /api/admin/push-stats?days=7

Response 200:
{
  "total": 42,
  "sent": 40,
  "failed": 2
}
```

### 赛道管理

```
GET    /api/admin/tracks           # 列出赛道配置
PATCH  /api/admin/tracks/{track_id}  # 更新赛道（enabled 等）
```

### 信号管理

```
GET    /api/signals                # 信号列表
PATCH  /api/signals/{id}/read      # 标记已读
GET    /api/dashboard/summary      # 仪表盘摘要
GET    /api/star-history          # Star 历史
```

---

## 三、WebSocket / SSE

### 实时信号流

```
GET /api/stream/signals

Headers:
  Accept: text/event-stream

Query Parameters:
  - track   可选：过滤赛道
  - token   必填：连接令牌（防止滥用）

Response: SSE 事件流
event: signal
data: {"id":71,"track_id":"bci","title":"...","priority":"high","created_at":"..."}

event: heartbeat
data: {"time":"2026-04-28T12:00:00"}
```

---

## 四、错误码

| HTTP Status | 说明 |
|-------------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在（如租户 ID 错误） |
| 409 | 冲突（如租户 ID 已存在） |
| 500 | 服务器内部错误 |

---

## 五、微信推送格式

当 Pipeline 推送信号到微信时，消息格式如下：

```
🚨 ⭐ 星标激增 | 项目名称

📊 Stars: 12,500 (+2,340 ↑)
🏷️ 赛道: AI大模型
📅 时间: 2026-04-28

💡 解读: LLM 发布后 7 天增长 23%，主要来自美国开发者社区...

---
📈 【脑机接口】深度分析仅对 Premium 租户开放
升级 Premium 获取：投资机会解读 / 竞争格局分析 / 风险提示 / 相关公司
联系我们升级账号 →
```
