"""
推送路由模块
负责：信号 → 租户 → 推送渠道 → 消息发送

设计原则：
- 一条信号生成后，所有订阅了该赛道的租户都会收到通知
- 每条 Alert 记录对应一个 (signal_id, tenant_id, channel)
- 租户可配置多个推送渠道（微信/飞书/邮件）
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

from ..core.database import get_db, Alert


# 推送渠道注册表
NOTIFIER_REGISTRY = {}


def register_notifier(channel: str, notifier_class):
    """注册推送渠道"""
    NOTIFIER_REGISTRY[channel] = notifier_class


def _load_notifiers():
    """懒加载所有推送渠道"""
    if not NOTIFIER_REGISTRY:
        from .wechat import WechatNotifier
        from .feishu import FeishuNotifier
        from .email import EmailNotifier
        register_notifier("wechat", WechatNotifier)
        register_notifier("feishu", FeishuNotifier)
        register_notifier("email", EmailNotifier)


class NotificationRouter:
    """
    多租户推送路由器

    使用方式：
        router = NotificationRouter()
        router.route_signals(signals)  # signals 含 tenant_ids
    """

    def __init__(self, db=None):
        self._db = db
        _load_notifiers()

    @property
    def db(self):
        if self._db is None:
            self._db = get_db()
        return self._db

    def route_signals(
        self,
        signals: List[Dict[str, Any]],
        track_id: str = None,
        target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将信号推送给所有相关租户。

        策略：
        - 读取每条信号的 tenant_ids
        - 对于每个租户，检查其通知偏好（渠道 + 阈值过滤）
        - 按渠道发送（微信/飞书/邮件）
        - 记录 Alert 到数据库

        Args:
            signals: 信号列表（已含 tenant_ids）
            track_id: 赛道ID（用于日志）
            target: 显式指定推送目标（如 "weixin:chat_id"，覆盖自动路由）

        Returns:
            推送结果 {"success": bool, "tenants_reached": int, "details": [...]}
        """
        if not signals:
            logger.info("[推送路由] 无信号，跳过")
            return {"success": True, "tenants_reached": 0, "details": []}

        results = {"success": True, "tenants_reached": 0, "details": []}

        # 收集所有需要推送的 (tenant_id, channel) 组合
        push_jobs = self._build_push_jobs(signals, target=target)

        if not push_jobs:
            logger.info("[推送路由] 无有效推送任务（可能无租户订阅）")
            return results

        logger.info(f"[推送路由] 开始推送：{len(push_jobs)} 个推送任务")
        results["tenants_reached"] = len(set(j["tenant_id"] for j in push_jobs))

        for job in push_jobs:
            ok = self._send_via_channel(
                content=job["content"],
                channel=job["channel"],
                target=job["target"],
                signal_id=job.get("signal_id"),
                tenant_id=job["tenant_id"],
            )
            job["ok"] = ok
            results["details"].append(job)
            if not ok:
                results["success"] = False

        return results

    def _build_push_jobs(
        self,
        signals: List[Dict[str, Any]],
        target: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        构建推送任务列表。

        Returns:
            List[{"tenant_id", "channel", "target", "content", "signal_id"}]
        """
        jobs = []

        for sig in signals:
            tenant_ids = sig.get("tenant_ids") or []
            signal_priority = sig.get("priority", "low")
            signal_id = sig.get("id")

            for tenant_id in tenant_ids:
                # 获取租户通知偏好
                pref = self.db.get_notification_pref(tenant_id)
                if not pref:
                    # 租户未配置推送，跳过
                    continue

                # 优先级过滤：租户设置 real_time_threshold
                if not self._passes_priority_filter(signal_priority, pref.real_time_threshold):
                    logger.debug(f"  跳过 {tenant_id}（信号优先级 {signal_priority} < 阈值 {pref.real_time_threshold}）")
                    continue

                # 微信渠道
                if pref.wechat_target or target:
                    wechat_target = target or pref.wechat_target
                    jobs.append({
                        "tenant_id": tenant_id,
                        "channel": "wechat",
                        "target": wechat_target,
                        "content": self._format_for_channel(sig, "wechat"),
                        "signal_id": signal_id,
                    })

                # 飞书渠道（预留）
                if pref.feishu_webhook:
                    jobs.append({
                        "tenant_id": tenant_id,
                        "channel": "feishu",
                        "target": pref.feishu_webhook,
                        "content": self._format_for_channel(sig, "feishu"),
                        "signal_id": signal_id,
                    })

                # 邮件渠道（预留）
                if pref.email:
                    jobs.append({
                        "tenant_id": tenant_id,
                        "channel": "email",
                        "target": pref.email,
                        "content": self._format_for_channel(sig, "email"),
                        "signal_id": signal_id,
                    })

        return jobs

    def _passes_priority_filter(self, signal_priority: str, threshold: str) -> bool:
        """判断信号优先级是否达到租户阈值"""
        priority_order = {"high": 3, "medium": 2, "low": 1}
        sig_level = priority_order.get(signal_priority, 0)
        threshold_level = priority_order.get(threshold, 2)
        return sig_level >= threshold_level

    def _format_for_channel(self, signal: dict, channel: str) -> str:
        """按渠道格式化消息"""
        _load_notifiers()
        notifier_cls = NOTIFIER_REGISTRY.get(channel)
        if not notifier_cls:
            return signal.get("content", signal.get("title", ""))
        try:
            notifier = notifier_cls()
            return notifier.format_signal_message(signal)
        except Exception:
            return signal.get("content", signal.get("title", ""))

    def _send_via_channel(
        self,
        content: str,
        channel: str,
        target: str,
        signal_id: Optional[int],
        tenant_id: str,
    ) -> bool:
        """通过指定渠道发送，并记录 Alert"""
        _load_notifiers()
        notifier_cls = NOTIFIER_REGISTRY.get(channel)
        if not notifier_cls:
            logger.warning(f"[推送路由] 未知渠道: {channel}")
            return False

        try:
            notifier = notifier_cls()
            ok = notifier.send_message(content, target=target)

            # 记录 Alert
            self._record_alert(
                signal_id=signal_id,
                tenant_id=tenant_id,
                channel=channel,
                status="sent" if ok else "failed",
            )
            return ok
        except Exception as e:
            logger.error(f"[推送路由] {channel} 推送失败: {e}")
            self._record_alert(
                signal_id=signal_id,
                tenant_id=tenant_id,
                channel=channel,
                status="failed",
                error_message=str(e),
            )
            return False

    def _record_alert(
        self,
        signal_id: Optional[int],
        tenant_id: str,
        channel: str,
        status: str,
        error_message: str = None,
    ):
        """记录 Alert 到数据库"""
        try:
            session = self.db.get_session()
            try:
                alert = Alert(
                    signal_id=signal_id,
                    tenant_id=tenant_id,
                    channel=channel,
                    status=status,
                    error_message=error_message,
                    sent_at=datetime.utcnow() if status == "sent" else None,
                )
                session.add(alert)
                session.commit()
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"[推送路由] Alert 记录失败: {e}")
