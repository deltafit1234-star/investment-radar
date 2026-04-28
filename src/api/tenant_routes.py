"""
投资雷达 - 多租户管理 API
路由：/api/v1/tenants, /api/v1/internal/webhooks

认证：天翼云平台回调验证（预留）
"""

from typing import Optional, List
from datetime import datetime
from loguru import logger

from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel


# ─── Request/Response Models ─────────────────────────────────────────

class TenantCreate(BaseModel):
    id: str
    name: str
    plan: str = "basic"


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None


class SubscriptionItem(BaseModel):
    track_id: str
    sensitivity: str = "medium"
    keywords_append: List[str] = []
    keywords_exclude: List[str] = []
    plan: str = "basic"
    enabled: bool = True


class SubscriptionsUpdate(BaseModel):
    subscriptions: List[SubscriptionItem]


class NotificationPrefUpdate(BaseModel):
    wechat_target: Optional[str] = None
    feishu_webhook: Optional[str] = None
    email: Optional[str] = None
    daily_brief_time: str = "08:30"
    real_time_alert_enabled: bool = True
    real_time_threshold: str = "medium"
    weekly_report_enabled: bool = False
    weekly_report_day: str = "monday"


class SubscriptionCallback(BaseModel):
    """天翼云平台订阅回调"""
    tenant_id: str
    tenant_name: str
    plan: str = "basic"
    subscriptions: List[SubscriptionItem]
    notification: Optional[NotificationPrefUpdate] = None


# ─── Router ─────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1", tags=["多租户管理"])


def _get_db():
    from src.core.database import get_db
    return get_db()


def _require_tenant(tenant_id: str):
    """验证租户存在"""
    db = _get_db()
    tenant = db.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"租户不存在: {tenant_id}")
    return tenant


def _get_tenant_plan(tenant_id: str) -> str:
    """获取租户 plan"""
    db = _get_db()
    tenant = db.get_tenant(tenant_id)
    return tenant.plan if tenant else "basic"


# ─── 租户管理 ─────────────────────────────────────────────────────

@router.get("/tenants")
def list_tenants():
    """列出所有租户"""
    db = _get_db()
    tenants = db.get_all_active_tenants()
    return [t.to_dict() for t in tenants]


@router.post("/tenants")
def create_tenant(data: TenantCreate):
    """创建租户"""
    db = _get_db()
    existing = db.get_tenant(data.id)
    if existing:
        raise HTTPException(status_code=409, detail="租户已存在")
    tenant = db.upsert_tenant(data.id, data.name, data.plan)
    return tenant.to_dict()


@router.get("/tenants/{tenant_id}")
def get_tenant(tenant_id: str):
    """获取租户详情"""
    _require_tenant(tenant_id)
    tenant = _require_tenant(tenant_id)
    return tenant.to_dict()


@router.put("/tenants/{tenant_id}")
def update_tenant(tenant_id: str, data: TenantUpdate):
    """更新租户"""
    db = _get_db()
    existing = _require_tenant(tenant_id)
    # upsert_tenant 会更新字段
    tenant = db.upsert_tenant(
        tenant_id,
        name=data.name or existing.name,
        plan=data.plan or existing.plan,
    )
    if data.is_active is not None:
        # is_active 需要单独处理（upsert 不支持）
        session = db.get_session()
        try:
            t = session.query(db.Tenant if hasattr(db, 'Tenant') else None).filter_by(id=tenant_id).first()
            if t:
                from src.core.database import Tenant
                t2 = session.query(Tenant).filter(Tenant.id == tenant_id).first()
                t2.is_active = data.is_active
                session.commit()
        finally:
            session.close()
    return tenant.to_dict()


@router.delete("/tenants/{tenant_id}")
def deactivate_tenant(tenant_id: str):
    """停用租户（软删除）"""
    db = _get_db()
    existing = _require_tenant(tenant_id)
    session = db.get_session()
    try:
        from src.core.database import Tenant
        t = session.query(Tenant).filter(Tenant.id == tenant_id).first()
        if t:
            t.is_active = False
            session.commit()
    finally:
        session.close()
    return {"ok": True, "message": f"租户 {tenant_id} 已停用"}


# ─── 订阅管理 ─────────────────────────────────────────────────────

@router.get("/tenants/{tenant_id}/subscriptions")
def get_subscriptions(tenant_id: str):
    """获取租户订阅列表"""
    _require_tenant(tenant_id)
    db = _get_db()
    subs = db.get_tenant_subscriptions(tenant_id, enabled_only=False)
    return [s.to_dict() for s in subs]


@router.put("/tenants/{tenant_id}/subscriptions")
def update_subscriptions(tenant_id: str, data: SubscriptionsUpdate):
    """批量更新租户订阅（幂等：覆盖已存在的，更新缺失的）"""
    _require_tenant(tenant_id)
    db = _get_db()
    results = []
    for item in data.subscriptions:
        sub = db.upsert_subscription(
            tenant_id=tenant_id,
            track_id=item.track_id,
            sensitivity=item.sensitivity,
            keywords_append=item.keywords_append,
            keywords_exclude=item.keywords_exclude,
            plan=item.plan,
            enabled=item.enabled,
        )
        results.append(sub.to_dict())
    return {"subscriptions": results}


@router.delete("/tenants/{tenant_id}/subscriptions/{track_id}")
def delete_subscription(tenant_id: str, track_id: str):
    """取消订阅某个赛道"""
    _require_tenant(tenant_id)
    db = _get_db()
    ok = db.delete_subscription(tenant_id, track_id)
    if not ok:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return {"ok": True}


# ─── 推送配置 ─────────────────────────────────────────────────────

@router.get("/tenants/{tenant_id}/notification")
def get_notification(tenant_id: str):
    """获取租户推送配置"""
    _require_tenant(tenant_id)
    db = _get_db()
    pref = db.get_notification_pref(tenant_id)
    if not pref:
        # 返回默认值
        return {
            "tenant_id": tenant_id,
            "wechat_target": None,
            "feishu_webhook": None,
            "email": None,
            "daily_brief_time": "08:30",
            "real_time_alert_enabled": True,
            "real_time_threshold": "medium",
            "weekly_report_enabled": False,
            "weekly_report_day": "monday",
        }
    return pref.to_dict()


@router.put("/tenants/{tenant_id}/notification")
def update_notification(tenant_id: str, data: NotificationPrefUpdate):
    """更新租户推送配置"""
    _require_tenant(tenant_id)
    db = _get_db()
    pref = db.upsert_notification_pref(
        tenant_id,
        wechat_target=data.wechat_target,
        feishu_webhook=data.feishu_webhook,
        email=data.email,
        daily_brief_time=data.daily_brief_time,
        real_time_alert_enabled=data.real_time_alert_enabled,
        real_time_threshold=data.real_time_threshold,
        weekly_report_enabled=data.weekly_report_enabled,
        weekly_report_day=data.weekly_report_day,
    )
    return pref.to_dict()


# ─── 信号查询 ─────────────────────────────────────────────────────

@router.get("/signals")
def get_signals(
    tenant_id: str = Query(..., description="租户ID"),
    track_id: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    plan: Optional[str] = Query("basic"),  # basic / premium
):
    """获取属于指定租户的信号（按 tenant_ids 过滤）"""
    _require_tenant(tenant_id)
    db = _get_db()
    signals = db.get_signals_for_tenant(
        tenant_id=tenant_id,
        track_id=track_id,
        priority=priority,
        limit=limit,
        offset=offset,
        tenant_plan=plan or "basic",
    )
    return {
        "data": signals,
        "tenant_id": tenant_id,
        "plan": plan or "basic",
        "count": len(signals),
    }


# ─── 赛道列表 ─────────────────────────────────────────────────────

@router.get("/tracks")
def list_tracks():
    """列出所有可用赛道（系统级，租户只读）"""
    from src.core.track_loader import get_all_tracks
    tracks = get_all_tracks()
    return [
        {
            "track_id": t["track_id"],
            "track_name": t["track_name"],
            "category": t.get("category", ""),
            "enabled": t.get("enabled", False),
            "description": t.get("description", ""),
        }
        for t in tracks
    ]


# ─── 内部回调 ─────────────────────────────────────────────────────

@router.post("/internal/webhooks/subscription")
def webhook_subscription(data: SubscriptionCallback):
    """
    天翼云平台订阅变更回调。

    平台通知我们：租户X订阅了赛道A/B，plan=premium，推送渠道配置...

    我们：
    1. 创建/更新租户
    2. 批量写入订阅
    3. 写入推送配置
    """
    db = _get_db()
    logger.info(f"[订阅回调] 租户={data.tenant_id} 订阅={len(data.subscriptions)}个赛道 plan={data.plan}")

    # 1. 创建/更新租户
    tenant = db.upsert_tenant(data.tenant_id, data.tenant_name, data.plan)

    # 2. 批量写入订阅
    for sub in data.subscriptions:
        db.upsert_subscription(
            tenant_id=data.tenant_id,
            track_id=sub.track_id,
            sensitivity=sub.sensitivity,
            keywords_append=sub.keywords_append,
            keywords_exclude=sub.keywords_exclude,
            plan=sub.plan,
            enabled=sub.enabled,
        )

    # 3. 写入推送配置（如果有）
    if data.notification:
        db.upsert_notification_pref(
            tenant_id=data.tenant_id,
            wechat_target=data.notification.wechat_target,
            feishu_webhook=data.notification.feishu_webhook,
            email=data.notification.email,
            daily_brief_time=data.notification.daily_brief_time,
            real_time_alert_enabled=data.notification.real_time_alert_enabled,
            real_time_threshold=data.notification.real_time_threshold,
            weekly_report_enabled=data.notification.weekly_report_enabled,
            weekly_report_day=data.notification.weekly_report_day,
        )

    logger.info(f"[订阅回调] {data.tenant_id} 处理完成")
    return {"ok": True, "tenant_id": data.tenant_id}
