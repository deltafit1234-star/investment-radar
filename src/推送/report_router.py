"""
每日情报报告推送路由（Phase 2）
将每日报告推送给 Premium 租户（按赛道分群）
复用信号推送渠道（wechat 分群推送）
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger


class ReportRouter:
    """
    日报推送路由器

    策略：
    - Premium 租户专属权益
    - 复用 NotificationRouter 的分群推送能力
    - 每个赛道独立推送，报告文本走同一渠道（wechat 分群）
    """

    def __init__(self):
        self.pushed_count = 0
        self.failed_count = 0

    def push_report(
        self,
        report: Dict[str, Any],
        tenant_id: str,
        channel: str = "wechat",
    ) -> bool:
        """
        推送单份日报给指定租户

        Args:
            report: DailyReportGenerator 生成的报告 dict
            tenant_id: 租户ID
            channel: 推送渠道（默认 wechat）

        Returns:
            bool: 是否成功
        """
        try:
            from src.推送.wechat import WechatNotifier

            notifier = WechatNotifier()
            report_text = report.get("report_text", "")

            if not report_text:
                logger.warning(f"  报告内容为空，跳过: {tenant_id}")
                return {"ok": False, "message": None, "wechat_target": None, "track_name": report.get("track_name") or ""}

            # 从租户配置获取推送目标
            target = self._get_tenant_target(tenant_id)
            if not target:
                logger.warning(f"  租户 {tenant_id} 未配置推送目标，跳过")
                return {"ok": False, "message": None, "wechat_target": None, "track_name": report.get("track_name") or ""}

            # 构建消息
            lines = [
                f"📊 每日投资情报报告",
                f"赛道: {report.get('track_name', report.get('track_id', ''))}",
                f"日期: {report.get('date', datetime.now().strftime('%Y-%m-%d'))}",
                "━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
            lines.append(report_text)
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━",
                "投资雷达 · Premium专属",
            ])

            message = "\n".join(lines)
            ok = notifier.send_message(message, target=target)

            result = {
                "ok": ok,
                "message": message,
                "wechat_target": target,
                "track_name": report.get("track_name") or report.get("track_id", ""),
            }
            if ok:
                self.pushed_count += 1
                logger.info(f"  ✅ 日报推送成功: {tenant_id} / {report.get('track_name')}")
            else:
                self.failed_count += 1
                logger.warning(f"  ❌ 日报推送失败: {tenant_id}")

            return result

        except Exception as e:
            logger.exception(f"  日报推送异常: {e}")
            self.failed_count += 1
            return {"ok": False, "message": None, "wechat_target": None, "track_name": report.get("track_name") or ""}

    def route_reports(
        self,
        reports: List[Dict[str, Any]],
        tenant_ids: List[str] = None,
    ) -> Dict[str, Any]:
        """
        批量路由推送多份日报

        Args:
            reports: 日报列表
            tenant_ids: 指定租户列表（None = 推送给所有 Premium 租户）

        Returns:
            {
                "reports_pushed": int,
                "reports_failed": int,
                "details": [...]
            }
        """
        if not reports:
            logger.info("无报告需要推送")
            return {"reports_pushed": 0, "reports_failed": 0, "details": []}

        # 确定要推送的租户
        if tenant_ids is None:
            tenant_ids = self._get_all_premium_tenant_ids()

        results = []
        for report in reports:
            track_id = report.get("track_id", "")
            for tenant_id in tenant_ids:
                # 检查租户是否订阅了该赛道
                if not self._tenant_subscribes_track(tenant_id, track_id):
                    continue

                push_result = self.push_report(report, tenant_id)
                ok = push_result.get("ok") if isinstance(push_result, dict) else push_result
                results.append({
                    "tenant_id": tenant_id,
                    "track_id": track_id,
                    "ok": ok,
                    "report_date": report.get("date"),
                    "message": push_result.get("message") if isinstance(push_result, dict) else None,
                    "wechat_target": push_result.get("wechat_target") if isinstance(push_result, dict) else None,
                })

        pushed = sum(1 for r in results if r["ok"])
        return {
            "reports_pushed": pushed,
            "reports_failed": len(results) - pushed,
            "total_reports": len(reports),
            "details": results,
        }

    def _get_tenant_target(self, tenant_id: str) -> Optional[str]:
        """从租户配置获取推送目标（wechat_target）"""
        try:
            from src.core.database import get_db
            db = get_db()
            session = db.get_session()
            try:
                from src.core.database import TenantNotificationPref
                pref = (
                    session.query(TenantNotificationPref)
                    .filter(TenantNotificationPref.tenant_id == tenant_id)
                    .first()
                )
                if pref and pref.wechat_target:
                    return pref.wechat_target
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"  获取租户推送目标失败: {e}")
        return None

    def _get_all_premium_tenant_ids(self) -> List[str]:
        """获取所有 Premium 活跃租户ID"""
        try:
            from src.core.database import get_db, Tenant
            db = get_db()
            session = db.get_session()
            try:
                tenants = (
                    session.query(Tenant)
                    .filter(Tenant.plan == "premium", Tenant.is_active == True)
                    .all()
                )
                return [t.id for t in tenants]
            finally:
                session.close()
        except Exception:
            return []

    def _tenant_subscribes_track(self, tenant_id: str, track_id: str) -> bool:
        """检查租户是否订阅了某赛道"""
        try:
            from src.core.database import get_db
            db = get_db()
            session = db.get_session()
            try:
                from src.core.database import TenantSubscription
                sub = (
                    session.query(TenantSubscription)
                    .filter(
                        TenantSubscription.tenant_id == tenant_id,
                        TenantSubscription.track_id == track_id,
                        TenantSubscription.enabled == True,
                    )
                    .first()
                )
                return sub is not None
            finally:
                session.close()
        except Exception:
            return False
