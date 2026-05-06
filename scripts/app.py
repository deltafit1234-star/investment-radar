#!/usr/bin/env python3
"""
投资雷达 - Web Dashboard + API Server
FastAPI 后端 + HTML 前端（Chart.js）
"""

import sys, os, argparse
from pathlib import Path
from datetime import datetime, timedelta

# 加载 .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
import uvicorn
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json

# ─── App Setup ────────────────────────────────────────────────
app = FastAPI(title="投资雷达", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ─── Database ────────────────────────────────────────────────
from src.core.database import get_db, init_db

# ─── 多租户 API ────────────────────────────────────────────────
from src.api.tenant_routes import router as tenant_router
app.include_router(tenant_router)


def _sig_to_api(sig) -> dict:
    """Signal ORM → API dict"""
    return {
        "id": sig.id,
        "track_id": sig.track_id,
        "source_id": sig.source_id,
        "signal_type": sig.signal_type,
        "title": sig.title,
        "content": sig.content,
        "priority": sig.priority,
        "meaning": sig.meaning,
        "is_read": sig.is_read,
        "created_at": sig.created_at.isoformat() if sig.created_at else None,
    }


# ─── REST API ────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/tracks")
def list_tracks():
    """列出所有赛道"""
    from src.core.track_loader import get_all_tracks
    tracks = get_all_tracks()
    return [
        {
            "track_id": t["track_id"],
            "track_name": t["track_name"],
            "category": t.get("category", ""),
            "enabled": t.get("enabled", False),
        }
        for t in tracks
    ]


@app.get("/api/signals")
def list_signals(
    track_id: str = Query(None, description="赛道ID，不传则所有赛道"),
    priority: str = Query(None, description="优先级 high/medium/low"),
    signal_type: str = Query(None, description="信号类型"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """信号列表"""
    db = get_db()
    signals = db.get_signals(track_id=track_id, priority=priority, limit=limit, offset=offset)

    # 按 signal_type 过滤
    if signal_type:
        signals = [s for s in signals if s.signal_type == signal_type]

    return {
        "total": len(signals),
        "signals": [_sig_to_api(s) for s in signals],
    }


@app.get("/api/signals/{signal_id}")
def get_signal(signal_id: int):
    """信号详情"""
    db = get_db()
    sig = db.get_signal_by_id(signal_id)
    if not sig:
        raise HTTPException(404, "Signal not found")
    return _sig_to_api(sig)


@app.patch("/api/signals/{signal_id}/read")
def mark_read(signal_id: int):
    """标记已读"""
    db = get_db()
    sig = db.update_signal(signal_id, {"is_read": True})
    if not sig:
        raise HTTPException(404, "Signal not found")
    return {"ok": True}


@app.get("/api/stats")
def stats(
    track_id: str = Query(None),
    days: int = Query(7, ge=1, le=90),
):
    """统计面板数据"""
    from src.core.database import get_db
    db = get_db()

    cutoff = datetime.utcnow() - timedelta(days=days)
    all_sigs = db.get_signals(track_id=track_id, limit=500)

    # 过滤时间范围
    sigs = [s for s in all_sigs if s.created_at and s.created_at.replace(tzinfo=None) >= cutoff.replace(tzinfo=None)]

    total = len(sigs)
    high = sum(1 for s in sigs if s.priority == "high")
    medium = sum(1 for s in sigs if s.priority == "medium")

    # 按信号类型分组
    by_type: dict = {}
    for s in sigs:
        t = s.signal_type or "unknown"
        by_type[t] = by_type.get(t, 0) + 1

    # 按天分组
    by_day: dict = {}
    for s in sigs:
        if s.created_at:
            day = s.created_at.strftime("%Y-%m-%d")
            by_day[day] = by_day.get(day, 0) + 1

    return {
        "total": total,
        "high": high,
        "medium": medium,
        "by_type": by_type,
        "by_day": by_day,
        "days": days,
    }


@app.get("/api/star-history")
def star_history(
    owner: str = Query(..., description="仓库所有者"),
    repo: str = Query(..., description="仓库名"),
    days: int = Query(7, ge=1, le=30),
):
    """GitHub Star 趋势"""
    db = get_db()
    records = db.get_star_trend(owner, repo, days=days)
    return {"owner": owner, "repo": repo, "history": records}


@app.get("/api/dashboard/summary")
def dashboard_summary():
    """Dashboard 概览数据"""
    from src.core.track_loader import get_enabled_tracks
    from src.core.database import get_db

    db = get_db()
    tracks = get_enabled_tracks()

    result = []
    for track in tracks:
        tid = track["track_id"]
        sigs = db.get_signals(track_id=tid, limit=200)
        week_cutoff = datetime.utcnow() - timedelta(days=7)
        week_sigs = [s for s in sigs if s.created_at and s.created_at.replace(tzinfo=None) >= week_cutoff.replace(tzinfo=None)]
        high_priority = sum(1 for s in week_sigs if s.priority == "high")

        result.append({
            "track_id": tid,
            "track_name": track["track_name"],
            "total_signals": len(sigs),
            "week_signals": len(week_sigs),
            "high_priority": high_priority,
        })

    return {"tracks": result, "generated_at": datetime.now().isoformat()}


# ─── SSE: 实时信号流 ─────────────────────────────────────────
@app.get("/api/stream/signals")
def stream_signals(
    track_id: str = Query(None, description="赛道ID"),
    last_id: int = Query(0, description="最后收到的信号ID，0则发最新信号"),
    poll_interval: int = Query(5, description="轮询间隔秒数"),
):
    """
    Server-Sent Events: 推送新信号（真实数据）

    客户端连接时带上 last_id（上次收到的最大信号ID），
    服务端返回 last_id 之后的所有新信号。

    响应格式: data: {...json...}\n\n
    """
    from src.core.database import get_db

    db = get_db()
    # 用 list 包装以便在嵌套生成器中修改（避免 UnboundLocalError）
    state = {"last_id": last_id}

    def event_generator():
        import time, json

        while True:
            # 取出 last_id 之后的新信号
            new_signals = db.get_signals_after(state["last_id"], track_id=track_id, limit=50)

            for sig in new_signals:
                payload = _sig_to_api(sig)
                state["last_id"] = max(state["last_id"], sig.id)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            # 如果是初始连接（last_id=0），无新信号时发一个心跳
            if state["last_id"] == 0:
                yield f"event: heartbeat\ndata: {{\"type\":\"heartbeat\",\"ts\":{int(time.time())}}}\n\n"

            time.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/admin/tracks")
def admin_list_tracks():
    """管理：所有赛道配置"""
    from src.core.track_loader import get_all_tracks
    tracks = get_all_tracks()
    return [{"track_id": t["track_id"], "track_name": t["track_name"], "category": t.get("category", ""), "enabled": t.get("enabled", False)} for t in tracks]


@app.patch("/api/admin/tracks/{track_id}")
def admin_toggle_track(track_id: str, enabled: bool = Query(..., description="启用/禁用")):
    """管理：启用/禁用赛道"""
    track_file = TRACKS_DIR / f"{track_id}.yaml"
    if not track_file.exists():
        raise HTTPException(404, "Track not found")

    with open(track_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config["enabled"] = enabled

    with open(track_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    return {"ok": True, "track_id": track_id, "enabled": enabled}


@app.get("/api/admin/alerts")
def admin_list_alerts(limit: int = Query(50, ge=1, le=200)):
    """管理：推送记录（alerts 表）"""
    db = get_db()
    session = db.get_session()
    try:
        from src.core.database import Alert
        alerts = session.query(Alert).order_by(Alert.created_at.desc()).limit(limit).all()
        return [{"id": a.id, "signal_id": a.signal_id, "tenant_id": a.tenant_id, "channel": a.channel, "status": a.status, "error_message": a.error_message, "sent_at": a.sent_at.isoformat() if a.sent_at else None, "created_at": a.created_at.isoformat() if a.created_at else None} for a in alerts]
    finally:
        session.close()


@app.get("/api/admin/push-stats")
def admin_push_stats(days: int = Query(7, ge=1, le=30)):
    """管理：推送统计"""
    db = get_db()
    session = db.get_session()
    try:
        from src.core.database import Alert
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        alerts = session.query(Alert).filter(Alert.created_at >= cutoff).all()
        total = len(alerts)
        sent = sum(1 for a in alerts if a.status == "sent")
        failed = sum(1 for a in alerts if a.status == "failed")
        pending = sum(1 for a in alerts if a.status == "pending")
        by_channel = {}
        for a in alerts:
            by_channel[a.channel] = by_channel.get(a.channel, 0) + 1
        return {"total": total, "sent": sent, "failed": failed, "pending": pending, "by_channel": by_channel, "days": days}
    finally:
        session.close()


# ─── 订阅管理 API ──────────────────────────────────────────────
@app.get("/api/subscription/packages")
def api_list_packages():
    """列出所有套餐"""
    from scripts.track_system import list_subscription_packages
    return list_subscription_packages()

@app.get("/api/subscription/status")
def api_subscription_status(tenant_id: str = Query(...)):
    """获取租户订阅状态"""
    from scripts.track_system import get_tenant_subscription
    sub = get_tenant_subscription(tenant_id)
    if not sub:
        return {"subscribed": False, "package_id": None}
    return {
        "subscribed": True,
        "package_id": sub["plan"],
        "package_name": sub.get("package_name", ""),
        "company_limit": sub.get("company_limit", 0),
        "keyword_limit": sub.get("keyword_limit", 0),
        "has_personalized": bool(sub.get("has_personalized_report")),
        "companies": sub.get("track_companies") or [],
        "keywords": sub.get("track_keywords") or [],
    }

@app.get("/api/subscription/companies")
def api_list_companies(tenant_id: str = Query(...)):
    """列出租户关注的公司"""
    from scripts.track_system import _get_companies
    return _get_companies(tenant_id)

@app.post("/api/subscription/companies")
def api_add_companies(tenant_id: str = Query(...), companies: list[str] = Query(...)):
    """添加关注公司"""
    from scripts.track_system import add_companies, get_tenant_subscription, _get_default_package
    from scripts.track_system import get_db
    conn = get_db()
    # Ensure subscription exists
    cur = conn.cursor()
    cur.execute("SELECT plan FROM tenant_subscriptions WHERE tenant_id=?", (tenant_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO tenant_subscriptions (tenant_id, track_id, plan, track_companies, track_keywords, enabled) VALUES (?,?,'starter','[]','[]',1)",
                   (tenant_id, tenant_id))
        conn.commit()
    conn.close()
    added = add_companies(tenant_id, companies)
    return {"added": added}

@app.delete("/api/subscription/companies")
def api_remove_companies(tenant_id: str = Query(...), companies: list[str] = Query(...)):
    """移除关注公司"""
    from scripts.track_system import remove_companies
    removed = remove_companies(tenant_id, companies)
    return {"removed": removed}

@app.get("/api/subscription/keywords")
def api_list_keywords(tenant_id: str = Query(...)):
    """列出租户关键词"""
    from scripts.track_system import _get_keywords
    return _get_keywords(tenant_id)

@app.post("/api/subscription/keywords")
def api_add_keywords(tenant_id: str = Query(...), keywords: list[str] = Query(...)):
    """添加关键词"""
    from scripts.track_system import add_keywords, get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT plan FROM tenant_subscriptions WHERE tenant_id=?", (tenant_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO tenant_subscriptions (tenant_id, track_id, plan, track_companies, track_keywords, enabled) VALUES (?,?,'starter','[]','[]',1)",
                   (tenant_id, tenant_id))
        conn.commit()
    conn.close()
    added = add_keywords(tenant_id, keywords)
    return {"added": added}

@app.delete("/api/subscription/keywords")
def api_remove_keywords(tenant_id: str = Query(...), keywords: list[str] = Query(...)):
    """移除关键词"""
    from scripts.track_system import remove_keywords
    removed = remove_keywords(tenant_id, keywords)
    return {"removed": removed}

@app.get("/api/subscription/personalized")
def api_personalized(tenant_id: str = Query(...), days: int = Query(7), limit: int = Query(20)):
    """获取个人化信号"""
    from scripts.track_system import get_personalized_signals
    return get_personalized_signals(tenant_id, days=days, limit=limit)


# ─── HTML Dashboard ────────────────────────────────────────────
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>投资雷达 - Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #0f1117; color: #e5e7eb; min-height: 100vh; }
.container { max-width: 1400px; margin: 0 auto; padding: 24px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; }
.header h1 { font-size: 28px; font-weight: 600; color: #f9fafb; }
.header .time { color: #6b7280; font-size: 14px; }

/* Track tabs */
.tabs { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
.tab { padding: 8px 20px; border-radius: 8px; background: #1f2937; color: #9ca3af; cursor: pointer; font-size: 14px; border: none; transition: all 0.2s; }
.tab:hover { background: #374151; color: #e5e7eb; }
.tab.active { background: #3b82f6; color: #fff; }

/* Stats cards */
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
.card { background: #1f2937; border-radius: 12px; padding: 20px; }
.card .label { color: #6b7280; font-size: 13px; margin-bottom: 8px; }
.card .value { font-size: 32px; font-weight: 700; color: #f9fafb; }
.card .sub { color: #6b7280; font-size: 12px; margin-top: 4px; }
.card.high .value { color: #ef4444; }
.card.medium .value { color: #f59e0b; }
.card.all .value { color: #3b82f6; }

/* Charts */
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }
.chart-card { background: #1f2937; border-radius: 12px; padding: 20px; }
.chart-card h3 { font-size: 15px; color: #9ca3af; margin-bottom: 16px; font-weight: 500; }
canvas { max-height: 220px; }

/* Signals table */
.signals { background: #1f2937; border-radius: 12px; overflow: hidden; }
.signals-header { padding: 16px 20px; border-bottom: 1px solid #374151; display: flex; justify-content: space-between; align-items: center; }
.signals-header h3 { font-size: 15px; font-weight: 500; color: #e5e7eb; }
.filters { display: flex; gap: 8px; }
select { background: #374151; color: #e5e7eb; border: none; padding: 6px 12px; border-radius: 6px; font-size: 13px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 10px 20px; color: #6b7280; font-size: 12px; font-weight: 500; border-bottom: 1px solid #374151; }
td { padding: 12px 20px; border-bottom: 1px solid #1f2937; font-size: 13px; }
tr:hover { background: #374151; }
tr.unread { background: #1e3a5f; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }
.badge.high { background: #7f1d1d; color: #fca5a5; }
.badge.medium { background: #78350f; color: #fcd34d; }
.badge.low { background: #1f2937; color: #9ca3af; }
.badge.star_surge { background: #1e3a5f; color: #93c5fd; }
.badge.paper_burst { background: #1e3a2f; color: #6ee7b7; }
.badge.funding_news { background: #3f1f5c; color: #d8b4fe; }
.badge.model_news { background: #1f3a1f; color: #86efac; }

.time-str { color: #6b7280; font-size: 12px; }
.track-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; background: #374151; color: #9ca3af; font-size: 11px; margin-left: 8px; }

.loading { text-align: center; padding: 40px; color: #6b7280; }
.refresh-btn { background: #374151; color: #e5e7eb; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.refresh-btn:hover { background: #4b5563; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📡 投资雷达</h1>
    <div class="time" id="clock"></div>
  </div>

  <!-- Track tabs -->
  <div style="display:flex; gap:8px; margin-bottom:24px; flex-wrap:wrap;">
    <button class="tab active" id="tabOverview" onclick="showTab('overview')">📊 概览</button>
    <button class="tab" id="tabAdmin" onclick="showTab('admin')">⚙️ 管理</button>
    <button class="tab" id="tabTenant" onclick="showTab('tenant')">🏢 多租户</button>
    <button class="tab" id="tabSubscription" onclick="showTab('subscription')">💎 订阅管理</button>
  </div>

  <!-- Live signals panel -->
  <div style="margin-bottom:24px; background:#1f2937; border-radius:12px; padding:16px 20px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <h3 style="font-size:15px; font-weight:500; color:#e5e7eb;">🔴 实时信号
        <span id="sseStatus" style="font-size:12px; color:#6b7280; font-weight:400; margin-left:8px;">连接中...</span>
      </h3>
      <div style="display:flex; gap:8px; align-items:center;">
        <select id="sseTrackFilter" style="background:#374151; color:#e5e7eb; border:none; padding:4px 10px; border-radius:6px; font-size:12px;">
          <option value="">全部赛道</option>
        </select>
        <button class="refresh-btn" id="sseToggle" onclick="toggleSSE()">暂停</button>
      </div>
    </div>
    <div id="liveSignals" style="max-height:200px; overflow-y:auto; font-size:13px;">
      <div style="color:#6b7280; padding:8px 0;">等待实时信号...</div>
    </div>
  </div>

  <!-- Stats -->
  <div class="stats" id="stats"></div>

  <!-- Charts -->
  <div class="charts" id="sectionCharts">
    <div class="chart-card">
      <h3>📊 信号趋势（近7天）</h3>
      <canvas id="trendChart"></canvas>
    </div>
    <div class="chart-card">
      <h3>📈 信号类型分布</h3>
      <canvas id="typeChart"></canvas>
    </div>
  </div>

  <!-- Signals table -->
  <div class="signals" id="sectionSignals">
    <div class="signals-header">
      <h3>📋 最新信号</h3>
      <div class="filters">
        <select id="filterTrack">
          <option value="">全部赛道</option>
        </select>
        <select id="filterPriority">
          <option value="">全部优先级</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
        </select>
        <select id="filterType">
          <option value="">全部类型</option>
          <option value="star_surge">Star 激增</option>
          <option value="paper_burst">论文爆发</option>
          <option value="funding_news">融资新闻</option>
          <option value="model_news">模型新闻</option>
        </select>
        <button class="refresh-btn" onclick="loadSignals()">🔄 刷新</button>
      </div>
    </div>
    <div id="signalsTable">
      <div class="loading">加载中...</div>
    </div>
  </div>

  <!-- Admin section (hidden by default) -->
  <div id="sectionAdmin" style="display:none">
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:24px;">
      <div class="card">
        <div class="label">近7天推送总数</div>
        <div class="value" id="pushTotal">-</div>
      </div>
      <div class="card">
        <div class="label">推送成功率</div>
        <div class="value" id="pushRate">-</div>
      </div>
    </div>

    <div class="signals">
      <div class="signals-header">
        <h3>🏁 赛道管理</h3>
      </div>
      <div id="adminTracks">
        <div class="loading">加载中...</div>
      </div>
    </div>

    <div class="signals" style="margin-top:16px;">
      <div class="signals-header">
        <h3>📨 推送记录</h3>
      </div>
      <div id="adminAlerts">
        <div class="loading">加载中...</div>
      </div>
    </div>
  </div>

  <!-- Multi-tenant section (hidden by default) -->
  <div id="sectionTenant" style="display:none">
    <!-- Tenant overview cards -->
    <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; margin-bottom:24px;">
      <div class="card">
        <div class="label">租户总数</div>
        <div class="value" id="tenantCount">-</div>
      </div>
      <div class="card">
        <div class="label">活跃订阅</div>
        <div class="value" id="tenantSubs">-</div>
      </div>
      <div class="card">
        <div class="label">已配置推送</div>
        <div class="value" id="tenantNotif">-</div>
      </div>
    </div>

    <!-- Create tenant form -->
    <div class="card" style="margin-bottom:20px; padding:16px;">
      <h3 style="font-size:14px; color:#e5e7eb; margin-bottom:12px;">➕ 创建租户</h3>
      <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
        <input id="newTenantId" placeholder="租户ID" style="background:#374151; color:#e5e7eb; border:1px solid #4b5563; padding:6px 10px; border-radius:6px; font-size:13px; width:160px;">
        <input id="newTenantName" placeholder="租户名称" style="background:#374151; color:#e5e7eb; border:1px solid #4b5563; padding:6px 10px; border-radius:6px; font-size:13px; width:180px;">
        <select id="newTenantPlan" style="background:#374151; color:#e5e7eb; border:1px solid #4b5563; padding:6px 10px; border-radius:6px; font-size:13px;">
          <option value="basic">Basic</option>
          <option value="premium">Premium</option>
        </select>
        <button class="refresh-btn" onclick="createTenant()">创建</button>
      </div>
    </div>

    <!-- Tenant list -->
    <div class="signals">
      <div class="signals-header">
        <h3>🏢 租户列表</h3>
        <button class="refresh-btn" onclick="loadTenantData()">🔄 刷新</button>
      </div>
      <div id="tenantList">
        <div class="loading">加载中...</div>
      </div>
    </div>
  </div>

  <!-- Subscription management (hidden by default) -->
  <div id="sectionSubscription" style="display:none">
    <!-- Subscription status -->
    <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:24px;">
      <div class="card">
        <div class="label">当前套餐</div>
        <div class="value" id="subPackage" style="font-size:20px;">-</div>
      </div>
      <div class="card">
        <div class="label">公司订阅</div>
        <div class="value" id="subCompanies" style="font-size:20px;">-</div>
      </div>
      <div class="card">
        <div class="label">关键词订阅</div>
        <div class="value" id="subKeywords" style="font-size:20px;">-</div>
      </div>
      <div class="card">
        <div class="label">个人化报告</div>
        <div class="value" id="subPersonalized" style="font-size:20px;">-</div>
      </div>
    </div>

    <!-- Tenant selector -->
    <div class="card" style="margin-bottom:20px; padding:16px;">
      <h3 style="font-size:14px; color:#e5e7eb; margin-bottom:12px;">👤 租户</h3>
      <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
        <input id="subTenantId" placeholder="租户ID（留空使用当前用户）" value="o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat" style="background:#374151; color:#e5e7eb; border:1px solid #4b5563; padding:6px 10px; border-radius:6px; font-size:13px; width:320px;">
        <button class="refresh-btn" onclick="loadSubscriptionData()">加载</button>
      </div>
    </div>

    <!-- Packages info -->
    <div class="signals" style="margin-bottom:20px;">
      <div class="signals-header">
        <h3>💎 套餐对比</h3>
      </div>
      <div id="packageList" style="padding:16px;"></div>
    </div>

    <!-- Company subscriptions -->
    <div class="signals" style="margin-bottom:20px;">
      <div class="signals-header">
        <h3>🏢 关注公司</h3>
      </div>
      <div style="padding:16px;">
        <div style="display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap;">
          <input id="newCompany" placeholder="输入公司名，回车添加" style="background:#374151; color:#e5e7eb; border:1px solid #4b5563; padding:6px 10px; border-radius:6px; font-size:13px; width:240px;">
          <button class="refresh-btn" onclick="addCompany()">添加公司</button>
        </div>
        <div id="companyTags" style="display:flex; gap:8px; flex-wrap:wrap;"></div>
      </div>
    </div>

    <!-- Keyword subscriptions -->
    <div class="signals" style="margin-bottom:20px;">
      <div class="signals-header">
        <h3>🔍 关键词订阅</h3>
      </div>
      <div style="padding:16px;">
        <div style="display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap;">
          <input id="newKeyword" placeholder="输入关键词，回车添加" style="background:#374151; color:#e5e7eb; border:1px solid #4b5563; padding:6px 10px; border-radius:6px; font-size:13px; width:240px;">
          <button class="refresh-btn" onclick="addKeyword()">添加关键词</button>
        </div>
        <div id="keywordTags" style="display:flex; gap:8px; flex-wrap:wrap;"></div>
      </div>
    </div>

    <!-- Personalized signals preview -->
    <div class="signals">
      <div class="signals-header">
        <h3>📌 个人化信号预览</h3>
        <button class="refresh-btn" onclick="loadPersonalizedSignals()">🔄 刷新</button>
      </div>
      <div id="personalizedSignals">
        <div class="loading">加载中...</div>
      </div>
    </div>
  </div>
</div>

<script>
// ── Clock ──────────────────────────────────────────────────
function updateClock() {
  document.getElementById("clock").textContent = new Date().toLocaleString("zh-CN");
}
updateClock();
setInterval(updateClock, 1000);

// ── API helpers ─────────────────────────────────────────────
const API = "/api";

async function api(endpoint) {
  const r = await fetch(API + endpoint);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

// ── Load tracks ─────────────────────────────────────────────
let currentTrack = "";

async function loadTracks() {
  try {
    const tracks = await api("/tracks");
    // Populate filter dropdown
    const sel = document.getElementById("filterTrack");
    if (sel) {
      sel.innerHTML = '<option value="">全部赛道</option>';
      tracks.forEach(t => {
        sel.innerHTML += `<option value="${t.track_id}">${t.track_name}</option>`;
      });
    }
  } catch (e) { console.error(e); }
}

// ── Load stats ──────────────────────────────────────────────
async function loadStats() {
  try {
    const data = await api("/stats?days=7&track_id=" + currentTrack);
    const container = document.getElementById("stats");
    container.innerHTML = `
      <div class="card all">
        <div class="label">本周信号总数</div>
        <div class="value">${data.total}</div>
        <div class="sub">近7天</div>
      </div>
      <div class="card high">
        <div class="label">高优先级</div>
        <div class="value">${data.high}</div>
        <div class="sub">需关注</div>
      </div>
      <div class="card medium">
        <div class="label">中优先级</div>
        <div class="value">${data.medium}</div>
        <div class="sub">持续观察</div>
      </div>
      <div class="card all">
        <div class="label">数据来源</div>
        <div class="value">${Object.keys(data.by_type).length}</div>
        <div class="sub">活跃信号类型</div>
      </div>
    `;

    // Trend chart
    const days = Object.keys(data.by_day).sort();
    const counts = days.map(d => data.by_day[d]);
    trendChart.data.labels = days;
    trendChart.data.datasets[0].data = counts;
    trendChart.update();

    // Type chart
    const types = Object.keys(data.by_type);
    const typeCounts = Object.values(data.by_type);
    typeChart.data.labels = types.map(t => ({star_surge:"Star激增",paper_burst:"论文爆发",funding_news:"融资",model_news:"模型"}[t]||t));
    typeChart.data.datasets[0].data = typeCounts;
    typeChart.update();
  } catch (e) { console.error(e); }
}

// ── Charts ───────────────────────────────────────────────────
const trendCtx = document.getElementById("trendChart").getContext("2d");
const trendChart = new Chart(trendCtx, {
  type: "line",
  data: { labels: [], datasets: [{ label: "信号数", data: [], borderColor: "#3b82f6", backgroundColor: "rgba(59,130,246,0.1)", tension: 0.4, fill: true }] },
  options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { grid: { color: "#1f2937" }, ticks: { color: "#6b7280" } }, y: { grid: { color: "#1f2937" }, ticks: { color: "#6b7280" } } } }
});

const typeCtx = document.getElementById("typeChart").getContext("2d");
const typeChart = new Chart(typeCtx, {
  type: "doughnut",
  data: { labels: [], datasets: [{ data: [], backgroundColor: ["#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6","#ec4899"] }] },
  options: { responsive: true, plugins: { legend: { position: "bottom", labels: { color: "#9ca3af" } } } }
});

// ── Load signals ─────────────────────────────────────────────
async function loadSignals() {
  const track = document.getElementById("filterTrack")?.value || currentTrack;
  const priority = document.getElementById("filterPriority")?.value || "";
  const stype = document.getElementById("filterType")?.value || "";

  let url = `/api/signals?limit=50&offset=0`;
  if (track) url += `&track_id=${encodeURIComponent(track)}`;
  if (priority) url += `&priority=${encodeURIComponent(priority)}`;
  if (stype) url += `&signal_type=${encodeURIComponent(stype)}`;

  try {
    const data = await api(url);
    renderSignals(data.signals || []);
  } catch (e) {
    document.getElementById("signalsTable").innerHTML = `<div class="loading">加载失败: ${e.message}</div>`;
  }
}

function createTableHTML() {
  return `<table>
    <thead><tr>
      <th>时间</th><th>赛道</th><th>类型</th><th>优先级</th><th>标题/内容</th>
    </tr></thead>
    <tbody id="signalsBody"></tbody>
  </table>`;
}

function renderSignals(signals) {
  const tbody = document.getElementById("signalsBody");
  if (!tbody) return;
  if (!signals.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#6b7280">暂无信号</td></tr>';
    return;
  }
  tbody.innerHTML = signals.map(s => `
    <tr class="${s.is_read ? '' : 'unread'}" onclick="markRead(${s.id})" style="cursor:pointer">
      <td><span class="time-str">${s.created_at ? s.created_at.slice(0,16).replace("T"," ") : "-"}</span></td>
      <td><span class="track-tag">${s.track_id || "-"}</span></td>
      <td><span class="badge ${s.signal_type}">${s.signal_type || "-"}</span></td>
      <td><span class="badge ${s.priority}">${s.priority}</span></td>
      <td><strong>${s.title || "-"}</strong><br><span style="color:#6b7280;font-size:12px">${(s.content||"").slice(0,80)}</span></td>
    </tr>
  `).join("");
}

async function markRead(id) {
  try {
    await api(`/signals/${id}/read`);
    loadSignals();
    loadStats();
  } catch(e) {}
}

function setTrack(track) {
  currentTrack = track;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  if (!track) {
    document.querySelector(".tab").classList.add("active");
  } else {
    document.querySelector(`.tab[onclick="setTrack('${track}')"]`)?.classList.add("active");
  }
  loadStats();
  loadSignals();
}

// ── Tab switching ─────────────────────────────────────────────
let currentTab = "overview";

function showTab(tab) {
  currentTab = tab;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.getElementById("tab" + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.add("active");

  document.getElementById("sectionCharts").style.display = tab === "overview" ? "" : "none";
  document.getElementById("sectionSignals").style.display = tab === "overview" ? "" : "none";
  document.getElementById("sectionAdmin").style.display = tab === "admin" ? "" : "none";
  document.getElementById("sectionTenant").style.display = tab === "tenant" ? "" : "none";
  document.getElementById("sectionSubscription").style.display = tab === "subscription" ? "" : "none";

  if (tab === "admin") loadAdminData();
  if (tab === "tenant") loadTenantData();
  if (tab === "subscription") loadSubscriptionData();
}

// ── Load admin data ──────────────────────────────────────────
async function loadAdminData() {
  // Push stats
  try {
    const stats = await api("/admin/push-stats?days=7");
    document.getElementById("pushTotal").textContent = stats.total || 0;
    const rate = stats.total > 0 ? Math.round((stats.sent / stats.total) * 100) : 0;
    document.getElementById("pushRate").textContent = rate + "%";
  } catch(e) { document.getElementById("pushTotal").textContent = "N/A"; }

  // Track list
  try {
    const tracks = await api("/admin/tracks");
    const container = document.getElementById("adminTracks");
    container.innerHTML = "<table><thead><tr><th>赛道</th><th>类别</th><th>状态</th><th>操作</th></tr></thead><tbody>" +
      tracks.map(t => `
        <tr>
          <td><strong>${t.track_name}</strong><br><span style="color:#6b7280;font-size:12px">${t.track_id}</span></td>
          <td>${t.category}</td>
          <td><span class="badge ${t.enabled ? 'low' : ''}" style="background:${t.enabled ? '#065f46' : '#7f1d1d'};color:${t.enabled ? '#6ee7b7' : '#fca5a5'}">${t.enabled ? '已启用' : '已禁用'}</span></td>
          <td><button class="refresh-btn" onclick="toggleTrack('${t.track_id}', ${!t.enabled})">${t.enabled ? '禁用' : '启用'}</button></td>
        </tr>`).join("") +
      "</tbody></table>";
  } catch(e) { document.getElementById("adminTracks").innerHTML = "<div class='loading'>加载失败</div>"; }

  // Alert history
  try {
    const alerts = await api("/admin/alerts?limit=20");
    const container = document.getElementById("adminAlerts");
    if (!alerts.length) {
      container.innerHTML = "<div style='padding:20px;color:#6b7280;text-align:center'>暂无推送记录</div>";
    } else {
      container.innerHTML = "<table><thead><tr><th>时间</th><th>信号ID</th><th>渠道</th><th>状态</th><th>错误</th></tr></thead><tbody>" +
        alerts.map(a => `
          <tr>
            <td><span class="time-str">${a.created_at ? a.created_at.slice(0,16) : "-"}</span></td>
            <td>${a.signal_id}</td>
            <td>${a.channel || "-"}</td>
            <td><span class="badge ${a.status === 'sent' ? 'low' : a.status === 'failed' ? 'high' : ''}" style="background:${a.status === 'sent' ? '#065f46' : a.status === 'failed' ? '#7f1d1d' : '#374151'};color:${a.status === 'sent' ? '#6ee7b7' : a.status === 'failed' ? '#fca5a5' : '#9ca3af'}">${a.status}</span></td>
            <td style="color:#ef4444;font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis">${a.error_message || "-"}</td>
          </tr>`).join("") +
        "</tbody></table>";
    }
  } catch(e) { document.getElementById("adminAlerts").innerHTML = "<div class='loading'>加载失败</div>"; }
}

async function toggleTrack(track_id, enable) {
  try {
    const r = await fetch(`/api/admin/tracks/${track_id}?enabled=${enable}`, {method: "PATCH"});
    if (!r.ok) throw new Error();
    loadAdminData();
  } catch(e) { alert("操作失败"); }
}

// ── SSE Real-time signals ───────────────────────────────────
let sseConn = null;
let ssePaused = false;
let lastSSEId = 0;
let sseTrackFilter = "";

function connectSSE() {
  if (sseConn) { sseConn.close(); }
  const trackParam = sseTrackFilter ? `&track_id=${encodeURIComponent(sseTrackFilter)}` : "";
  sseConn = new EventSource(`/api/stream/signals?last_id=${lastSSEId}${trackParam}&poll_interval=5`);

  sseConn.onopen = () => {
    document.getElementById("sseStatus").textContent = "已连接";
    document.getElementById("sseStatus").style.color = "#10b981";
  };

  sseConn.onmessage = (e) => {
    if (ssePaused) return;
    try {
      const sig = JSON.parse(e.data);
      if (sig.id) {
        lastSSEId = Math.max(lastSSEId, sig.id);
        prependLiveSignal(sig);
        // Also update total count in stats
        loadStats();
      }
    } catch(err) { console.error(err); }
  };

  sseConn.onerror = () => {
    document.getElementById("sseStatus").textContent = "断连重连中...";
    document.getElementById("sseStatus").style.color = "#f59e0b";
    sseConn.close();
    setTimeout(connectSSE, 5000);
  };
}

function toggleSSE() {
  ssePaused = !ssePaused;
  document.getElementById("sseToggle").textContent = ssePaused ? "恢复" : "暂停";
}

function prependLiveSignal(sig) {
  const container = document.getElementById("liveSignals");
  if (!container) return;
  // Remove placeholder if present
  if (container.querySelector(".loading") || container.querySelector("div[style*='等待']")) {
    container.innerHTML = "";
  }
  const priorityColor = sig.priority === "high" ? "#ef4444" : sig.priority === "medium" ? "#f59e0b" : "#6b7280";
  const typeLabel = {"star_surge":"⭐","paper_burst":"📄","funding_news":"💰","model_news":"🤖"}[sig.signal_type] || "📌";
  const time = sig.created_at ? sig.created_at.slice(11,16) : "";
  const html = `<div style="padding:8px 0; border-bottom:1px solid #374151; animation: fadeIn 0.3s ease">
    <span style="color:${priorityColor}; font-weight:600">${sig.priority}</span>
    <span style="margin-left:8px; color:#9ca3af">${typeLabel}</span>
    <span style="margin-left:8px; color:#e5e7eb">${(sig.title||"").slice(0,60)}</span>
    <span style="float:right; color:#6b7280; font-size:12px">${time}</span>
  </div>`;
  container.insertAdjacentHTML("afterbegin", html);
  // Keep max 20 items
  const items = container.querySelectorAll("div[style*='border-bottom']");
  if (items.length > 20) items[items.length-1].remove();
}

function updateSSETackFilter() {
  sseTrackFilter = document.getElementById("sseTrackFilter")?.value || "";
  connectSSE();
}

// ── Init ────────────────────────────────────────────────────
loadTracks();
loadStats();
loadSignals();
connectSSE();

// Populate SSE track filter from tracks
document.getElementById("sseTrackFilter")?.addEventListener("change", updateSSETackFilter);

setInterval(() => { if (!ssePaused) { loadStats(); loadSignals(); } }, 60000);  // 每分钟刷新

// ── Multi-tenant Management ────────────────────────────────────
async function loadTenantData() {
  try {
    const tenants = await api("/v1/tenants");
    const tracks = await api("/v1/tracks");
    const trackMap = {};
    tracks.forEach(t => trackMap[t.track_id] = t.track_name);

    // Overview stats
    document.getElementById("tenantCount").textContent = tenants.length;
    let totalSubs = 0, totalNotif = 0;
    const subPromises = tenants.map(async t => {
      try {
        const subs = await api(`/v1/tenants/${t.id}/subscriptions`);
        const notif = await api(`/v1/tenants/${t.id}/notification`);
        t._subscriptions = subs;
        t._notification = notif;
        totalSubs += subs.length;
        totalNotif += (notif.wechat_target || notif.email ? 1 : 0);
      } catch(e) { t._subscriptions = []; t._notification = {}; }
    });
    await Promise.all(subPromises);

    document.getElementById("tenantCount").textContent = tenants.length;
    document.getElementById("tenantSubs").textContent = totalSubs;
    document.getElementById("tenantNotif").textContent = totalNotif;

    // Render tenant list
    const container = document.getElementById("tenantList");
    if (tenants.length === 0) {
      container.innerHTML = '<div style="padding:40px; text-align:center; color:#6b7280;">暂无租户，请使用上方表单创建</div>';
      return;
    }

    let html = `<table>
      <thead><tr>
        <th>租户</th><th>Plan</th><th>订阅赛道</th><th>推送配置</th><th>创建时间</th><th>操作</th>
      </tr></thead><tbody>`;

    tenants.forEach(t => {
      const subs = t._subscriptions || [];
      const notif = t._notification || {};
      const subTags = subs.length > 0
        ? subs.map(s => `<span class="track-tag">${trackMap[s.track_id] || s.track_id}</span>`).join(' ')
        : '<span style="color:#6b7280;font-size:12px">暂无订阅</span>';
      const notifInfo = [
        notif.wechat_target ? `微信: ${notif.wechat_target.slice(0,15)}...` : null,
        notif.email ? `邮件: ${notif.email}` : null,
      ].filter(Boolean).join('<br>') || '<span style="color:#6b7280;font-size:12px">未配置</span>';
      const planColor = t.plan === 'premium' ? '#d8b4fe' : '#9ca3af';
      const created = t.created_at ? new Date(t.created_at).toLocaleDateString("zh-CN") : '-';
      html += `<tr>
        <td><strong style="color:#e5e7eb">${t.name}</strong><br><span style="color:#6b7280;font-size:11px">${t.id}</span></td>
        <td><span style="color:${planColor};font-size:12px;font-weight:500">${t.plan.toUpperCase()}</span></td>
        <td>${subTags}</td>
        <td style="font-size:12px;color:#9ca3af">${notifInfo}</td>
        <td style="color:#6b7280;font-size:12px">${created}</td>
        <td>
          <button class="refresh-btn" style="padding:4px 8px;font-size:11px" onclick="deleteTenant('${t.id}')">删除</button>
        </td>
      </tr>`;
    });

    html += '</tbody></table>';
    container.innerHTML = html;
  } catch(e) {
    document.getElementById("tenantList").innerHTML = `<div style="padding:40px; text-align:center; color:#ef4444;">加载失败: ${e.message}</div>`;
  }
}

async function createTenant() {
  const id = document.getElementById("newTenantId").value.trim();
  const name = document.getElementById("newTenantName").value.trim();
  const plan = document.getElementById("newTenantPlan").value;
  if (!id || !name) { alert("请填写租户ID和名称"); return; }
  try {
    await api("/v1/tenants", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, name, plan }),
    });
    document.getElementById("newTenantId").value = "";
    document.getElementById("newTenantName").value = "";
    loadTenantData();
  } catch(e) { alert("创建失败: " + e.message); }
}

async function deleteTenant(tenantId) {
  if (!confirm(`确定停用租户 ${tenantId}？`)) return;
  try {
    await api(`/v1/tenants/${tenantId}`, { method: "DELETE" });
    loadTenantData();
  } catch(e) { alert("删除失败: " + e.message); }
}

// ── Subscription Management ────────────────────────────────────
async function loadSubscriptionData() {
  const tenantId = document.getElementById("subTenantId").value.trim() || "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat";

  // Load packages
  try {
    const packages = await api("/subscription/packages");
    const container = document.getElementById("packageList");
    container.innerHTML = `<table style="width:100%;font-size:13px;">
      <thead><tr><th>套餐</th><th>公司限额</th><th>关键词限额</th><th>个人化报告</th><th>月费</th></tr></thead>
      <tbody>` +
      packages.map(p => {
        const isCurrent = p.id === document.getElementById("subPackage").textContent ||
          (p.id === "free" && document.getElementById("subPackage").textContent === "-");
        return `<tr style="${isCurrent ? 'background:#1e3a5f' : ''}">
          <td><strong style="color:${p.id === 'pro' ? '#f59e0b' : p.id === 'enterprise' ? '#ef4444' : '#e5e7eb'}">${p.name}</strong> ${isCurrent ? '✓' : ''}</td>
          <td>${p.company_limit || '无限制'}</td>
          <td>${p.keyword_limit || '无限制'}</td>
          <td>${p.has_personalized_report ? '✅' : '❌'}</td>
          <td>¥${p.price_monthly || 0}/月</td>
        </tr>`;
      }).join("") + `</tbody></table>`;
  } catch(e) { document.getElementById("packageList").innerHTML = "<div style='padding:16px;color:#ef4444'>加载失败</div>"; }

  // Load subscription status
  try {
    const status = await api(`/subscription/status?tenant_id=${encodeURIComponent(tenantId)}`);
    if (!status.subscribed) {
      document.getElementById("subPackage").textContent = "未订阅";
      document.getElementById("subCompanies").textContent = "0";
      document.getElementById("subKeywords").textContent = "0";
      document.getElementById("subPersonalized").textContent = "❌";
    } else {
      document.getElementById("subPackage").textContent = status.package_name || status.package_id;
      const companies = status.companies || [];
      const keywords = status.keywords || [];
      document.getElementById("subCompanies").textContent = `${companies.length}/${status.company_limit || '∞'}`;
      document.getElementById("subKeywords").textContent = `${keywords.length}/${status.keyword_limit || '∞'}`;
      document.getElementById("subPersonalized").textContent = status.has_personalized ? "✅" : "❌";
    }
  } catch(e) { console.error("加载订阅状态失败", e); }

  // Load company tags
  try {
    const companies = await api(`/subscription/companies?tenant_id=${encodeURIComponent(tenantId)}`);
    const container = document.getElementById("companyTags");
    container.innerHTML = (companies || []).map(c =>
      `<span style="background:#1e3a5f;color:#93c5fd;padding:4px 12px;border-radius:12px;font-size:13px;display:inline-flex;align-items:center;gap:6px;">
        ${c}
        <span onclick="removeCompany('${c}')" style="cursor:pointer;color:#fca5a5;font-weight:bold;margin-left:2px;">×</span>
      </span>`
    ).join("");
    if (!companies || !companies.length) container.innerHTML = "<span style='color:#6b7280;font-size:13px;'>暂无关注公司</span>";
  } catch(e) { document.getElementById("companyTags").innerHTML = "<span style='color:#ef4444'>加载失败</span>"; }

  // Load keyword tags
  try {
    const keywords = await api(`/subscription/keywords?tenant_id=${encodeURIComponent(tenantId)}`);
    const container = document.getElementById("keywordTags");
    container.innerHTML = (keywords || []).map(k =>
      `<span style="background:#1e3a2f;color:#6ee7b7;padding:4px 12px;border-radius:12px;font-size:13px;display:inline-flex;align-items:center;gap:6px;">
        ${k}
        <span onclick="removeKeyword('${k}')" style="cursor:pointer;color:#fca5a5;font-weight:bold;margin-left:2px;">×</span>
      </span>`
    ).join("");
    if (!keywords || !keywords.length) container.innerHTML = "<span style='color:#6b7280;font-size:13px;'>暂无关键词</span>";
  } catch(e) { document.getElementById("keywordTags").innerHTML = "<span style='color:#ef4444'>加载失败</span>"; }

  loadPersonalizedSignals();
}

async function loadPersonalizedSignals() {
  const tenantId = document.getElementById("subTenantId").value.trim() || "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat";
  const container = document.getElementById("personalizedSignals");
  try {
    const data = await api(`/subscription/personalized?tenant_id=${encodeURIComponent(tenantId)}&days=7&limit=20`);
    const co = data.company_signals || [];
    const kw = data.keyword_signals || [];
    if (!co.length && !kw.length) {
      container.innerHTML = "<div style='padding:20px;text-align:center;color:#6b7280;font-size:14px;'>暂无匹配信号（信号库近期无相关动态）</div>";
      return;
    }
    let html = "";
    if (co.length) {
      html += `<div style="padding:12px 16px;background:#1e3a5f;color:#93c5fd;font-size:13px;font-weight:500;">🏢 公司订阅信号（${co.length}条）</div>`;
      co.forEach(s => { html += `<div style="padding:10px 16px;border-bottom:1px solid #374151;font-size:13px;">[${s.signal_type}] ${s.title || '-'} <span style="color:#6b7280;margin-left:8px;">${(s.content||'').slice(0,60)}</span></div>`; });
    }
    if (kw.length) {
      html += `<div style="padding:12px 16px;background:#1e3a2f;color:#6ee7b7;font-size:13px;font-weight:500;margin-top:8px;">🔍 关键词订阅信号（${kw.length}条）</div>`;
      kw.forEach(s => { html += `<div style="padding:10px 16px;border-bottom:1px solid #374151;font-size:13px;">[${s.signal_type}] ${s.title || '-'} <span style="color:#6b7280;margin-left:8px;">${(s.content||'').slice(0,60)}</span></div>`; });
    }
    container.innerHTML = html;
  } catch(e) { container.innerHTML = "<div style='padding:20px;color:#ef4444'>加载失败: " + e.message + "</div>"; }
}

async function addCompany() {
  const tenantId = document.getElementById("subTenantId").value.trim() || "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat";
  const input = document.getElementById("newCompany");
  const name = input.value.trim();
  if (!name) return;
  try {
    await api(`/subscription/companies?tenant_id=${encodeURIComponent(tenantId)}&companies=${encodeURIComponent(name)}`, {method:"POST"});
    input.value = "";
    loadSubscriptionData();
  } catch(e) { alert("添加失败: " + e.message); }
}

async function removeCompany(name) {
  const tenantId = document.getElementById("subTenantId").value.trim() || "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat";
  try {
    await api(`/subscription/companies?tenant_id=${encodeURIComponent(tenantId)}&companies=${encodeURIComponent(name)}`, {method:"DELETE"});
    loadSubscriptionData();
  } catch(e) { alert("移除失败: " + e.message); }
}

async function addKeyword() {
  const tenantId = document.getElementById("subTenantId").value.trim() || "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat";
  const input = document.getElementById("newKeyword");
  const name = input.value.trim();
  if (!name) return;
  try {
    await api(`/subscription/keywords?tenant_id=${encodeURIComponent(tenantId)}&keywords=${encodeURIComponent(name)}`, {method:"POST"});
    input.value = "";
    loadSubscriptionData();
  } catch(e) { alert("添加失败: " + e.message); }
}

async function removeKeyword(name) {
  const tenantId = document.getElementById("subTenantId").value.trim() || "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat";
  try {
    await api(`/subscription/keywords?tenant_id=${encodeURIComponent(tenantId)}&keywords=${encodeURIComponent(name)}`, {method:"DELETE"});
    loadSubscriptionData();
  } catch(e) { alert("移除失败: " + e.message); }
}

// Enter key support
document.getElementById("newCompany")?.addEventListener("keydown", e => { if (e.key === "Enter") addCompany(); });
document.getElementById("newKeyword")?.addEventListener("keydown", e => { if (e.key === "Enter") addKeyword(); });
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_alias():
    return DASHBOARD_HTML


# ─── CLI ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="投资雷达 Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式")
    args = parser.parse_args()

    # 初始化数据库
    init_db()
    logger.info(f"数据库初始化完成")

    logger.info(f"启动 Dashboard: http://{args.host}:{args.port}")
    uvicorn.run(
        "scripts.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
