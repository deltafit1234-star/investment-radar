#!/usr/bin/env python3
"""
投资雷达 - 持续跟踪系统
支持系统规则驱动 + 租户人工标注两种模式
"""
import os, json, sqlite3, re
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = "/mnt/c/Users/Admin/Desktop/investment-radar"
DB_PATH = f"{PROJECT_DIR}/data/radar.db"

# ── 规则定义 ────────────────────────────────────────────────────────────────
# type: funding | company | policy | keyword | source
# action: track | ignore
DEFAULT_RULES = [
    {"id": "rule_funding_100m",  "type": "funding",  "threshold": 100_000_000,  "action": "track",  "label": "亿级融资"},
    {"id": "rule_policy_具身",   "type": "keyword",  "keywords": ["具身智能", "人形机器人"], "action": "track", "label": "政策热点"},
    {"id": "rule_company_figure","type": "company",  "names": ["Figure", "1X Technologies", "Agility Robotics", "Boston Dynamics"], "action": "track", "label": "明星公司"},
    {"id": "rule_source_policy", "type": "source",   "sources": ["policy_news"], "action": "track", "label": "政策来源"},
    {"id": "rule_high_priority", "type": "priority", "levels": ["high", "urgent"], "action": "track", "label": "高优先级"},
]

# ── 数据库 ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_track_tables():
    """初始化跟踪系统所需表"""
    conn = get_db()
    cur = conn.cursor()

    # 跟踪规则表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS track_rules (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,          -- funding|company|policy|keyword|source|priority
            label TEXT,
            config JSON NOT NULL,        -- 规则配置
            action TEXT NOT NULL,         -- track|ignore
            enabled INTEGER DEFAULT 1,
            tenant_id TEXT,               -- NULL表示全局规则
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 持续跟踪项目表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tracked_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            track_type TEXT NOT NULL,     -- manual|rule
            rule_id TEXT,
            tenant_id TEXT,               -- manual时指定租户，rule时可为NULL(全局)
            reason TEXT,                  -- 跟踪原因描述
            status TEXT DEFAULT 'active', -- active|resolved|archived
            first_seen_at DATETIME,
            last_updated_at DATETIME,
            update_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(signal_id, tenant_id)
        )
    """)

    # 跟踪项目更新记录
    cur.execute("""
        CREATE TABLE IF NOT EXISTS track_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracked_signal_id INTEGER NOT NULL,
            signal_id INTEGER NOT NULL,
            update_type TEXT NOT NULL,   -- new_signal|content_change|funding_update|policy_update
            update_summary TEXT,
            update_data JSON,
            seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tracked_signal_id) REFERENCES tracked_signals(id)
        )
    """)

    # 租户跟踪配置（人工标注权限）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tenant_track_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            track_mode TEXT DEFAULT 'hybrid',  -- manual|rule|hybrid|none
            auto_track_enabled INTEGER DEFAULT 1,
            notification_enabled INTEGER DEFAULT 1,
            config JSON,                        -- 租户特定规则覆盖
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id)
        )
    """)

    conn.commit()
    conn.close()

def seed_default_rules():
    """写入默认规则（仅插入不存在的）"""
    conn = get_db()
    cur = conn.cursor()
    for rule in DEFAULT_RULES:
        cur.execute("SELECT id FROM track_rules WHERE id=?", (rule["id"],))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO track_rules (id, type, label, config, action)
                VALUES (?, ?, ?, ?, ?)
            """, (rule["id"], rule["type"], rule["label"], json.dumps({k:v for k,v in rule.items() if k not in ("id","type","label","action")}), rule["action"]))
    conn.commit()
    conn.close()

# ── 规则引擎 ────────────────────────────────────────────────────────────────
def eval_funding_rule(rule_config, signal):
    """融资金额阈值规则"""
    threshold = rule_config.get("threshold", 50_000_000)
    content = signal.get("content", "") or ""
    titles = signal.get("title", "") or ""
    text = titles + content
    # 匹配亿级数字
    amounts = re.findall(r'(\d+)\s*[亿Y]', text)
    for amt in amounts:
        if int(amt) * 100_000_000 >= threshold:
            return True, f"融资金额{int(amt)}亿 ≥ {threshold//100_000_000}亿阈值"
    return False, None

def eval_keyword_rule(rule_config, signal):
    """关键词匹配规则"""
    keywords = rule_config.get("keywords", [])
    content = signal.get("content", "") or ""
    titles = signal.get("title", "") or ""
    text = titles + content
    matched = [kw for kw in keywords if kw in text]
    if matched:
        return True, f"匹配关键词: {', '.join(matched)}"
    return False, None

def eval_company_rule(rule_config, signal):
    """公司名匹配规则"""
    names = rule_config.get("names", [])
    content = signal.get("content", "") or ""
    titles = signal.get("title", "") or ""
    text = titles + content
    matched = [n for n in names if n.lower() in text.lower()]
    if matched:
        return True, f"匹配公司: {', '.join(matched)}"
    return False, None

def eval_source_rule(rule_config, signal):
    """来源类型规则"""
    sources = rule_config.get("sources", [])
    if signal.get("track_id") in sources or signal.get("source_id") in sources:
        return True, f"来源: {signal.get('track_id') or signal.get('source_id')}"
    return False, None

def eval_priority_rule(rule_config, signal):
    """优先级规则"""
    levels = rule_config.get("levels", [])
    if signal.get("priority") in levels:
        return True, f"优先级: {signal.get('priority')}"
    return False, None

RULE_EVALUATORS = {
    "funding":   eval_funding_rule,
    "keyword":   eval_keyword_rule,
    "company":   eval_company_rule,
    "source":    eval_source_rule,
    "priority":  eval_priority_rule,
}

def evaluate_signal(signal, rules=None):
    """评估单条信号，返回匹配的规则列表[(rule, reason)]"""
    if rules is None:
        rules = get_active_rules()
    matched = []
    for rule in rules:
        evaluator = RULE_EVALUATORS.get(rule["type"])
        if not evaluator:
            continue
        config = rule.get("config", {})
        if isinstance(config, str):
            config = json.loads(config)
        hit, reason = evaluator(config, signal)
        if hit:
            matched.append((rule, reason))
    return matched

def get_active_rules(tenant_id=None):
    """获取启用的规则"""
    conn = get_db()
    cur = conn.cursor()
    if tenant_id:
        cur.execute("""
            SELECT * FROM track_rules
            WHERE enabled=1 AND (tenant_id IS NULL OR tenant_id=?)
            ORDER BY tenant_id NULLS FIRST
        """, (tenant_id,))
    else:
        cur.execute("SELECT * FROM track_rules WHERE enabled=1")
    rules = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rules

# ── 跟踪管理 ────────────────────────────────────────────────────────────────
def add_tracked_signal(signal_id, track_type, tenant_id=None, rule_id=None, reason=None):
    """添加跟踪项目（已存在则忽略）"""
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    try:
        cur.execute("""
            INSERT INTO tracked_signals
                (signal_id, track_type, tenant_id, rule_id, reason, status, first_seen_at, last_updated_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
        """, (signal_id, track_type, tenant_id, rule_id, reason, now, now))
        conn.commit()
        added = True
    except sqlite3.IntegrityError:
        added = False  # 已存在
    conn.close()
    return added

def get_tracked_signals(tenant_id=None, status="active"):
    """获取当前跟踪项目"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT ts.*, s.title, s.content, s.signal_type, s.priority, s.track_id, s.source_id, s.created_at as signal_created
        FROM tracked_signals ts
        JOIN signals s ON ts.signal_id = s.id
        WHERE ts.status=? AND (ts.tenant_id IS NULL OR ts.tenant_id=?)
        ORDER BY ts.last_updated_at DESC
    """, (status, tenant_id))
    rows = [dict(r) for r in cur.fetchall()]

    # 补充最新更新
    for row in rows:
        cur.execute("""
            SELECT * FROM track_updates
            WHERE tracked_signal_id=? AND update_type='new_signal'
            ORDER BY seen_at DESC LIMIT 1
        """, (row["id"],))
        update = cur.fetchone()
        row["latest_update"] = dict(update) if update else None
    conn.close()
    return rows

def resolve_tracked_signal(tracked_id, tenant_id=None):
    """标记为已解决"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE tracked_signals SET status='resolved', last_updated_at=?
        WHERE id=? AND (tenant_id IS NULL OR tenant_id=?)
    """, (datetime.now().isoformat(), tracked_id, tenant_id))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

def archive_tracked_signal(tracked_id, tenant_id=None):
    """归档跟踪项目"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE tracked_signals SET status='archived', last_updated_at=?
        WHERE id=? AND (tenant_id IS NULL OR tenant_id=?)
    """, (datetime.now().isoformat(), tracked_id, tenant_id))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

# ── 信号处理 ────────────────────────────────────────────────────────────────
def process_signal_for_tracking(signal, tenant_id=None):
    """处理新信号：评估规则 + 决定是否跟踪"""
    conn = get_db()
    cur = conn.cursor()

    # 查询已有跟踪项
    cur.execute("SELECT signal_id FROM tracked_signals WHERE status='active'")
    already_tracked = {r["signal_id"] for r in cur.fetchall()}
    conn.close()

    if signal["id"] in already_tracked:
        return []  # 已在跟踪

    # 评估规则
    rules = get_active_rules(tenant_id)
    matched = evaluate_signal(signal, rules)

    added = []
    for rule, reason in matched:
        ok = add_tracked_signal(
            signal_id=signal["id"],
            track_type="rule",
            rule_id=rule["id"],
            reason=reason
        )
        if ok:
            added.append((rule, reason))
    return added

def scan_new_signals_for_tracking(days=1, tenant_id=None):
    """扫描近N天新信号，匹配规则并添加跟踪"""
    conn = get_db()
    cur = conn.cursor()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT * FROM signals
        WHERE created_at >= ? AND has_premium_content=1
        ORDER BY created_at DESC
    """, (since,))
    signals = [dict(r) for r in cur.fetchall()]
    conn.close()

    results = []
    for sig in signals:
        added = process_signal_for_tracking(sig, tenant_id)
        if added:
            results.append((sig, added))
    return results

def record_signal_update(tracked_signal_id, signal_id, update_type, summary=None, data=None):
    """记录信号更新"""
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("""
        INSERT INTO track_updates (tracked_signal_id, signal_id, update_type, update_summary, update_data, seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (tracked_signal_id, signal_id, update_type, summary, json.dumps(data) if data else None, now))

    # 更新计数 + 时间
    cur.execute("""
        UPDATE tracked_signals
        SET update_count=update_count+1, last_updated_at=?
        WHERE id=?
    """, (now, tracked_signal_id))
    conn.commit()
    conn.close()

def check_tracked_signals_for_updates(days=7, tenant_id=None):
    """检查跟踪项目的最新相关信号"""
    conn = get_db()
    cur = conn.cursor()

    # 获取活跃跟踪项
    cur.execute("""
        SELECT ts.*, s.title, s.content, s.keywords, s.signal_type
        FROM tracked_signals ts
        JOIN signals s ON ts.signal_id = s.id
        WHERE ts.status='active' AND (ts.tenant_id IS NULL OR ts.tenant_id=?)
    """, (tenant_id,))
    tracked = [dict(r) for r in cur.fetchall()]
    conn.close()

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    updates = []

    for item in tracked:
        # 用关键词 + 原始信号ID 查询相关新信号
        keywords = json.loads(item.get("keywords") or "[]")
        search_terms = [item["title"]] + keywords[:3] if keywords else [item["title"]]

        conn = get_db()
        cur = conn.cursor()
        conditions = " OR ".join(["title LIKE ? OR content LIKE ?" for _ in search_terms])
        params = [f"%{t}%" for t in search_terms] * 2
        cur.execute(f"""
            SELECT * FROM signals
            WHERE created_at >= ? AND ({conditions})
            ORDER BY created_at DESC LIMIT 5
        """, [since] + params)
        related = [dict(r) for r in cur.fetchall() if r["id"] != item["signal_id"]]
        conn.close()

        for rel in related:
            if rel["id"] == item["signal_id"]:
                continue  # 跳过自身
            # 查这条是否已记录过
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM track_updates WHERE tracked_signal_id=? AND signal_id=?", (item["id"], rel["id"]))
            exists = cur.fetchone()
            conn.close()
            if not exists:
                record_signal_update(item["id"], rel["id"], "new_signal",
                    summary=f"相关更新: {rel['title'][:50]}",
                    data={"title": rel["title"], "type": rel["signal_type"]})
                updates.append((item, rel))
    return updates

# ── 租户配置 ────────────────────────────────────────────────────────────────
def get_tenant_track_config(tenant_id):
    """获取租户跟踪配置"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tenant_track_config WHERE tenant_id=?", (tenant_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def upsert_tenant_track_config(tenant_id, **kwargs):
    """更新租户跟踪配置"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tenant_track_config (tenant_id, track_mode, auto_track_enabled, notification_enabled, config)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id) DO UPDATE SET
            track_mode=excluded.track_mode,
            auto_track_enabled=excluded.auto_track_enabled,
            notification_enabled=excluded.notification_enabled,
            config=excluded.config,
            updated_at=CURRENT_TIMESTAMP
    """, (
        tenant_id,
        kwargs.get("track_mode", "hybrid"),
        kwargs.get("auto_track_enabled", 1),
        kwargs.get("notification_enabled", 1),
        json.dumps(kwargs.get("config", {}))
    ))
    conn.commit()
    conn.close()

def tenant_add_watch(tenant_id, signal_id, reason=None):
    """租户人工标注跟踪"""
    return add_tracked_signal(signal_id, "manual", tenant_id=tenant_id, reason=reason or "人工标注")

def tenant_remove_watch(tenant_id, signal_id):
    """租户取消跟踪"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE tracked_signals SET status='archived'
        WHERE signal_id=? AND tenant_id=? AND track_type='manual'
    """, (signal_id, tenant_id))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

# ── 报告集成 ────────────────────────────────────────────────────────────────
def get_tracked_for_report(tenant_id=None, limit=10):
    """获取供报告使用的跟踪项目（含最新动态）"""
    items = get_tracked_signals(tenant_id=tenant_id, status="active")

    result = []
    for item in items[:limit]:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM track_updates
            WHERE tracked_signal_id=? AND update_type='new_signal'
            ORDER BY seen_at DESC LIMIT 3
        """, (item["id"],))
        updates = [dict(r) for r in cur.fetchall()]
        conn.close()
        result.append({
            "signal_id": item["signal_id"],
            "title": item["title"],
            "track_type": item["track_type"],
            "reason": item["reason"],
            "first_seen": item["first_seen_at"],
            "last_updated": item["last_updated_at"],
            "update_count": item["update_count"],
            "recent_updates": updates
        })
    return result

# ── 订阅管理 ────────────────────────────────────────────────────────────────
def get_tenant_subscription(tenant_id):
    """获取租户订阅信息"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT ts.*, sp.name as package_name, sp.company_limit, sp.keyword_limit,
               sp.has_personalized_report, sp.price_monthly
        FROM tenant_subscriptions ts
        LEFT JOIN subscription_packages sp ON ts.plan = sp.id
        WHERE ts.tenant_id=?
    """, (tenant_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_subscription_package(package_id):
    """获取套餐信息"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscription_packages WHERE id=?", (package_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def list_subscription_packages():
    """列出所有套餐"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscription_packages ORDER BY price_monthly")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def _get_companies(tenant_id):
    """读取租户公司列表"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT track_companies FROM tenant_subscriptions WHERE tenant_id=?", (tenant_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0])
    return []

def _set_companies(tenant_id, companies):
    """写入租户公司列表"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tenant_subscriptions SET track_companies=? WHERE tenant_id=?", (json.dumps(companies, ensure_ascii=False), tenant_id))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected == 0:
        # 租户不存在则插入
        cur.execute("INSERT INTO tenant_subscriptions (tenant_id, track_companies, track_keywords, plan, enabled) VALUES (?,?,'[]',?,1)",
                    (tenant_id, json.dumps(companies, ensure_ascii=False), _get_default_package()))
    conn.commit()
    conn.close()

def _get_keywords(tenant_id):
    """读取租户关键词列表"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT track_keywords FROM tenant_subscriptions WHERE tenant_id=?", (tenant_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0])
    return []

def _set_keywords(tenant_id, keywords):
    """写入租户关键词列表"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE tenant_subscriptions SET track_keywords=? WHERE tenant_id=?", (json.dumps(keywords, ensure_ascii=False), tenant_id))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected == 0:
        cur.execute("INSERT INTO tenant_subscriptions (tenant_id, track_companies, track_keywords, plan, enabled) VALUES (?,'[]',?,?,1)",
                    (tenant_id, json.dumps(keywords, ensure_ascii=False), _get_default_package()))
    conn.commit()
    conn.close()

def _get_default_package():
    return "free"

def add_companies(tenant_id, companies):
    """追加公司到订阅列表"""
    existing = _get_companies(tenant_id)
    # 检查套餐上限
    pkg = get_subscription_package(_get_tenant_package(tenant_id))
    limit = pkg.get("company_limit") if pkg else 0
    for c in companies:
        if c not in existing:
            if limit is not None and len(existing) >= limit and limit > 0:
                return {"ok": False, "error": f"公司订阅已达上限({limit}家)", "current": existing}
            existing.append(c)
    _set_companies(tenant_id, existing)
    return {"ok": True, "companies": existing}

def remove_companies(tenant_id, companies):
    """从订阅列表移除公司"""
    existing = _get_companies(tenant_id)
    updated = [c for c in existing if c not in companies]
    _set_companies(tenant_id, updated)
    return {"ok": True, "companies": updated}

def add_keywords(tenant_id, keywords):
    """追加关键词到订阅列表"""
    existing = _get_keywords(tenant_id)
    pkg = get_subscription_package(_get_tenant_package(tenant_id))
    limit = pkg.get("keyword_limit") if pkg else 10
    for k in keywords:
        if k not in existing:
            if limit is not None and len(existing) >= limit:
                return {"ok": False, "error": f"关键词订阅已达上限({limit}个)", "current": existing}
            existing.append(k)
    _set_keywords(tenant_id, existing)
    return {"ok": True, "keywords": existing}

def remove_keywords(tenant_id, keywords):
    """从订阅列表移除关键词"""
    existing = _get_keywords(tenant_id)
    updated = [k for k in existing if k not in keywords]
    _set_keywords(tenant_id, updated)
    return {"ok": True, "keywords": updated}

def _get_tenant_package(tenant_id):
    """获取租户套餐ID"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT plan FROM tenant_subscriptions WHERE tenant_id=?", (tenant_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else _get_default_package()

# ── 订阅信号匹配 ────────────────────────────────────────────────────────────────
def match_signal_for_subscriptions(signal):
    """
    对入库信号，检查所有租户的公司订阅匹配情况。
    返回：[(tenant_id, signal_id, matched_company), ...]
    """
    conn = get_db()
    cur = conn.cursor()
    # 查所有有公司订阅且有个人化报告权限的租户
    cur.execute("""
        SELECT ts.tenant_id, ts.track_companies, sp.has_personalized_report
        FROM tenant_subscriptions ts
        JOIN subscription_packages sp ON ts.plan = sp.id
        WHERE ts.enabled=1 AND sp.has_personalized_report=1
          AND ts.track_companies IS NOT NULL AND ts.track_companies != '[]'
    """)
    rows = cur.fetchall()
    conn.close()

    title = signal.get("title") or ""
    content = signal.get("content") or ""
    text = (title + " " + content).lower()

    results = []
    for tenant_id, track_companies_json, has_report in rows:
        companies = json.loads(track_companies_json) if track_companies_json else []
        for company in companies:
            if company.lower() in text:
                results.append((tenant_id, signal["id"], company))
    return results

def process_subscription_matching(signal):
    """
    处理信号的订阅匹配，写入 tracked_signals。
    """
    matched = match_signal_for_subscriptions(signal)
    for tenant_id, signal_id, company in matched:
        conn = get_db()
        cur = conn.cursor()
        try:
            now = datetime.now().isoformat()
            cur.execute("""
                INSERT INTO tracked_signals
                    (signal_id, track_type, tenant_id, matched_company, reason, status, first_seen_at, last_updated_at)
                VALUES (?, 'company_subscription', ?, ?, ?, 'active', ?, ?)
            """, (signal_id, tenant_id, company, f"公司订阅匹配: {company}", now, now))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # 已在跟踪
        finally:
            conn.close()
    return matched

def get_personalized_signals(tenant_id, days=7, limit=20):
    """
    获取付费租户个人化信号（公司订阅实时匹配 + 关键词订阅报告时匹配）。
    返回格式：{"company_signals": [...], "keyword_signals": [...]}
    """
    conn = get_db()
    cur = conn.cursor()

    # 公司订阅：从 tracked_signals 查
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT ts.*, s.title, s.content, s.signal_type, s.priority, s.track_id, s.created_at
        FROM tracked_signals ts
        JOIN signals s ON ts.signal_id = s.id
        WHERE ts.tenant_id=? AND ts.status='active'
          AND ts.track_type='company_subscription'
          AND ts.last_updated_at >= ?
        ORDER BY ts.last_updated_at DESC
        LIMIT ?
    """, (tenant_id, since, limit))
    company_signals = [dict(r) for r in cur.fetchall()]

    # 关键词订阅：从 signals 表按关键词全文匹配
    keywords = _get_keywords(tenant_id)
    keyword_signals = []
    if keywords:
        conditions = " OR ".join(["(title LIKE ? OR content LIKE ?)"] * len(keywords))
        params = [f"%{kw}%" for kw in keywords for _ in range(2)]
        cur.execute(f"""
            SELECT * FROM signals
            WHERE created_at >= ? AND ({conditions})
            ORDER BY created_at DESC LIMIT ?
        """, [since] + params + [limit])
        keyword_signals = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {"company_signals": company_signals, "keyword_signals": keyword_signals}

# ── 轻量 API（FastAPI）───────────────────────────────────────────────────────
"""
启动方式: uvicorn scripts.track_system:app --host 0.0.0.0 --port 7860
租户通过 ?tenant_id=xxx 查询
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="投资雷达-跟踪系统")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class WatchRequest(BaseModel):
    reason: Optional[str] = None

class ConfigRequest(BaseModel):
    track_mode: Optional[str] = None
    auto_track_enabled: Optional[int] = None
    notification_enabled: Optional[int] = None

# ── 订阅 API ────────────────────────────────────────────────────────────────
class CompanyListRequest(BaseModel):
    companies: list[str]

class KeywordListRequest(BaseModel):
    keywords: list[str]

@app.get("/api/subscriptions")
def api_get_subscriptions(tenant_id: str = Query(...)):
    """获取租户完整订阅状态"""
    sub = get_tenant_subscription(tenant_id)
    if not sub:
        raise HTTPException(404, "租户不存在")
    return {
        "tenant_id": tenant_id,
        "package": sub.get("package_name", "免费版"),
        "has_personalized_report": bool(sub.get("has_personalized_report")),
        "companies": _get_companies(tenant_id),
        "keywords": _get_keywords(tenant_id),
        "company_limit": sub.get("company_limit"),
        "keyword_limit": sub.get("keyword_limit"),
    }

@app.put("/api/subscriptions/companies")
def api_add_companies(body: CompanyListRequest, tenant_id: str = Query(...)):
    """追加公司订阅"""
    result = add_companies(tenant_id, body.companies)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result

@app.delete("/api/subscriptions/companies")
def api_remove_companies(body: CompanyListRequest, tenant_id: str = Query(...)):
    """移除公司订阅"""
    return remove_companies(tenant_id, body.companies)

@app.get("/api/subscriptions/companies")
def api_list_companies(tenant_id: str = Query(...)):
    """查询公司订阅列表"""
    return {"companies": _get_companies(tenant_id)}

@app.put("/api/subscriptions/keywords")
def api_add_keywords(body: KeywordListRequest, tenant_id: str = Query(...)):
    """追加关键词订阅"""
    result = add_keywords(tenant_id, body.keywords)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return result

@app.delete("/api/subscriptions/keywords")
def api_remove_keywords(body: KeywordListRequest, tenant_id: str = Query(...)):
    """移除关键词订阅"""
    return remove_keywords(tenant_id, body.keywords)

@app.get("/api/subscriptions/keywords")
def api_list_keywords(tenant_id: str = Query(...)):
    """查询关键词订阅列表"""
    return {"keywords": _get_keywords(tenant_id)}

@app.get("/api/packages")
def api_list_packages():
    """列出所有套餐"""
    return {"packages": list_subscription_packages()}

@app.get("/api/personalized")
def api_personalized(tenant_id: str = Query(...), days: int = Query(7), limit: int = Query(20)):
    """获取个人化信号（付费租户专属）"""
    sub = get_tenant_subscription(tenant_id)
    if not sub:
        raise HTTPException(404, "租户不存在")
    if not sub.get("has_personalized_report"):
        raise HTTPException(403, "该套餐无个人化报告权限")
    return get_personalized_signals(tenant_id, days=days, limit=limit)

@app.get("/api/track")
def api_list_tracked(tenant_id: str = Query(...), status: str = Query("active")):
    """列出当前跟踪项目"""
    items = get_tracked_signals(tenant_id=tenant_id, status=status)
    return {"count": len(items), "items": items}

@app.post("/api/track/{signal_id}")
def api_add_watch(signal_id: int, body: WatchRequest, tenant_id: str = Query(...)):
    """人工标注跟踪"""
    ok = tenant_add_watch(tenant_id, signal_id, reason=body.reason)
    if not ok:
        raise HTTPException(400, "已在跟踪或信号不存在")
    return {"ok": True, "signal_id": signal_id}

@app.delete("/api/track/{signal_id}")
def api_remove_watch(signal_id: int, tenant_id: str = Query(...)):
    """取消人工跟踪"""
    ok = tenant_remove_watch(tenant_id, signal_id)
    if not ok:
        raise HTTPException(400, "未找到或无权删除")
    return {"ok": True}

@app.get("/api/track/updates")
def api_updates(tenant_id: str = Query(...), limit: int = Query(20)):
    """获取跟踪项目最新动态"""
    tracked = get_tracked_for_report(tenant_id=tenant_id, limit=limit)
    return {"count": len(tracked), "items": tracked}

@app.get("/api/rules")
def api_list_rules(tenant_id: Optional[str] = Query(None)):
    """列出当前生效规则"""
    rules = get_active_rules(tenant_id=tenant_id)
    return {"count": len(rules), "rules": [{"id": r["id"], "type": r["type"], "label": r["label"], "action": r["action"]} for r in rules]}

@app.get("/api/rules/config")
def api_rules_config():
    """返回可配置的规则模板"""
    return {
        "types": ["funding", "company", "policy", "keyword", "source", "priority"],
        "default_rules": DEFAULT_RULES,
        "descriptions": {
            "funding":  "融资金额阈值（threshold: 最小金额，分/万/亿）",
            "company":  "公司名称列表（names: list[str]）",
            "policy":   "政策关键词（keywords: list[str]）",
            "keyword":  "通用关键词（keywords: list[str]）",
            "source":   "信号来源类型（sources: list[track_id]）",
            "priority": "优先级（levels: list[high|medium|low]）",
        }
    }

@app.post("/api/config/track")
def api_upsert_config(body: ConfigRequest, tenant_id: str = Query(...)):
    """更新租户跟踪配置"""
    upsert_tenant_track_config(tenant_id, **body.dict(exclude_none=True))
    return {"ok": True}

@app.get("/api/config/track")
def api_get_config(tenant_id: str = Query(...)):
    """获取租户跟踪配置"""
    cfg = get_tenant_track_config(tenant_id)
    if not cfg:
        return {"tenant_id": tenant_id, "track_mode": "hybrid", "auto_track_enabled": 1, "notification_enabled": 1}
    return cfg

# ── 初始化 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_track_tables()
    seed_default_rules()

    # 扫描近期信号
    print("🔍 扫描近期信号匹配跟踪规则...")
    results = scan_new_signals_for_tracking(days=7)
    if results:
        print(f"\n📌 新增跟踪项目 {len(results)} 个:")
        for sig, matched in results:
            print(f"  [{sig['id']}] {sig['title'][:50]}")
            for rule, reason in matched:
                print(f"      → {rule['label']}: {reason}")
    else:
        print("✅ 无新增匹配")

    # 检查现有跟踪项的更新
    print("\n🔄 检查跟踪项目最新动态...")
    updates = check_tracked_signals_for_updates(days=7)
    if updates:
        print(f"📰 {len(updates)} 条新动态:")
        for item, rel in updates:
            print(f"  [{item['title'][:30]}] ← {rel['title'][:40]}")
    else:
        print("✅ 无新动态")

    # 打印当前跟踪列表
    print("\n📋 当前活跃跟踪项目:")
    tracked = get_tracked_signals(status="active")
    for t in tracked:
        print(f"  [{t['track_type']:6}] #{t['id']} signal={t['signal_id']} | {t['title'][:40]} | 更新{t['update_count']}次 | {t['reason']}")
