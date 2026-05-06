# 投资雷达 · 租户订阅系统方案 v1.1

> 状态：待确认
> 日期：2026-05-06

---

## 一、核心场景

租户订阅公司/产品（付费）或赛道/关键词（免费/付费），接收其关注标的的相关信号。个人化订阅内容为付费专属价值点。

---

## 二、订阅类型与评估规则

| 类型 | 适用版本 | 评估时机 | 交付方式 |
|---|---|---|---|
| **赛道/关键词订阅** | 免费版可用 | 报告生成时评估 | 日报：赛道内容；周报：无个人化章节 |
| **公司/产品订阅** | 付费专属 | 每条新信号入库时实时评估 | 日报 + 周报均有"您的关注动态"章节 |

**免费版周报：** 所有免费用户收到同一份普通版周报，无个人化内容。

**评估规则细节：**

- **公司/产品订阅**：对入库新信号，在 `title` 和 `content` 中全文匹配公司名（不区分大小写），命中则写入 `tracked_signals`，状态 `track_type='company'`。优先限 `funding_news / product_news / policy_news` 类型。
- **赛道/关键词订阅**：在报告生成时，对该租户近 N 天信号按关键词全文匹配，免费版归入日报赛道内容，付费版归入专属章节。

---

## 三、数据模型

### 3.1 扩展 `tenant_subscriptions` 表

```sql
ALTER TABLE tenant_subscriptions ADD COLUMN track_companies JSON;
-- 示例: ["Figure", "1X Technologies", "追觅"]
ALTER TABLE tenant_subscriptions ADD COLUMN track_keywords JSON;
-- 示例: ["具身智能", "人形机器人", "Embodied AI"]
```

### 3.2 新建 `subscription_packages` 表

```sql
CREATE TABLE subscription_packages (
    id TEXT PRIMARY KEY,           -- "starter" / "pro" / "enterprise"
    name TEXT,                      -- "基础版" / "专业版" / "企业版"
    company_limit INTEGER,          -- 公司订阅数量上限，NULL=不限
    keyword_limit INTEGER,          -- 关键词订阅数量上限
    has_personalized_report INTEGER, -- 是否拥有个人化报告章节
    price_monthly REAL,             -- 月费
    created_at DATETIME
);
```

### 3.3 扩展 `tracked_signals` 表

```sql
ALTER TABLE tracked_signals ADD COLUMN matched_company TEXT;
-- 命中的公司名（用于去重展示）
```

---

## 四、套餐设计

| 套餐 | 月费 | 公司订阅上限 | 关键词上限 | 个人化章节 |
|---|---|---|---|---|
| **免费版** | ¥0 | 0 | 10 | ❌ 周报无个人化章节 |
| **基础版** | ¥49 | 5 家 | 30 | ✅ 日报+周报均有 |
| **专业版** | ¥99 | 20 家 | 100 | ✅ 日报+周报均有 |
| **企业版** | ¥299 | 100 家 | 不限 | ✅ 日报+周报均有 |

> 公司订阅与关键词订阅为**两套独立计费体系**，可叠加购买。

---

## 五、订阅管理 API

### 5.1 公司订阅

```
PUT  /api/subscriptions/companies
DELETE /api/subscriptions/companies
GET  /api/subscriptions/companies?tenant_id=xxx
```

### 5.2 关键词订阅

```
PUT  /api/subscriptions/keywords
DELETE /api/subscriptions/keywords
GET  /api/subscriptions/keywords?tenant_id=xxx
```

### 5.3 套餐查询

```
GET /api/packages
```

---

## 六、报告集成

### 6.1 日报

- **免费版**：按订阅赛道展示相关信号（关键词匹配）
- **付费版**：公司订阅命中的信号单独展示为"您的关注动态"（实时）

### 6.2 周报

- **免费版**：统一普通版，无个人化章节
- **付费版**：在普通版基础上增加"您的关注动态"章节（公司订阅结果 + 关键词订阅结果）

### 6.3 报告生成流程

```
gen_weekly_reports.py
  │
  ├── 读取订阅租户列表（含套餐信息）
  │
  ├── 对每位付费租户：
  │     ├── 公司订阅 → tracked_signals 表查近7天匹配
  │     ├── 关键词订阅 → signals 表匹配
  │     └── 生成个人化 JSON → 渲染 PDF
  │
  └── 统一普通版 PDF（免费版用户共用）
```

---

## 七、实施顺序

### Phase 1（本週）
- [ ] 数据库：`track_companies` / `track_keywords` 字段 + `subscription_packages` 表
- [ ] API：公司订阅和关键词订阅的增删查
- [ ] 信号处理：公司名匹配 → `tracked_signals`
- [ ] 报告章节：日报 + 周报"您的关注动态"（仅付费租户）

### Phase 2（后续）
- [ ] 租户后台管理界面
- [ ] 套餐校验（数量上限）
- [ ] 推送机制（微信/邮件）
- [ ] 付费流程

---

## 八、待确认事项

~~1. **日报个人化章节**~~ → ✅ 付费版日报+周报均有"您的关注动态"
~~2. **套餐数量阶梯**~~ → ✅ 基础5/专业20/企业100
~~3. **公司订阅与关键词订阅计费**~~ → ✅ 独立计费，可叠加，费用合并
~~4. **免费版日报形态**~~ → ✅ 简单展示订阅赛道信号，不做特殊筛选

---

## 九、技术约束（已知）

- 数据库 content 使用全角竖线 `｜`（U+FF5C），公司名匹配注意编码
- 通用词（"苹果"、"腾讯"）误匹配问题：目前方案限 signal_type 过滤，暂不做 LLM 消歧
- 多租户架构：所有表按 tenant_id 隔离，推送通道（微信/邮件）通过 alerts 表或 router 接口预留

