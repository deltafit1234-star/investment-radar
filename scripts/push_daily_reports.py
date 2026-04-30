#!/usr/bin/env python3
"""
投资雷达 - 推送今日日报（供 cron 调用）
直接调用 WeChat API 推送，不依赖 Hermes relay
"""
import asyncio, os, sys
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path.home() / ".hermes/hermes-agent"))

from src.推送.report_router import ReportRouter
from src.core.database import get_db, DailyReport
from gateway.platforms.weixin import send_weixin_direct


def push_today_reports():
    today = os.environ.get("REPORT_DATE") or __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    session = db.get_session()

    try:
        reports = (
            session.query(DailyReport)
            .filter(DailyReport.report_date == today)
            .all()
        )
        if not reports:
            print(f"[推送] 今日({today})无报告，跳过", flush=True)
            return

        reports_data = [r.report_data for r in reports if r.report_data]
        print(f"[推送] 今日({today})找到 {len(reports_data)} 份报告，开始推送...", flush=True)

        router = ReportRouter()
        result = router.route_reports(reports_data)
        total = result.get("reports_pushed", 0)
        failed = result.get("reports_failed", 0)
        details = result.get("details", [])

        # 实际发送微信消息
        async def send_all():
            token = os.getenv("WEIXIN_TOKEN")
            account_id = os.getenv("WEIXIN_ACCOUNT_ID")
            if not token or not account_id:
                print("  [错误] WEIXIN_TOKEN 或 WEIXIN_ACCOUNT_ID 未配置", flush=True)
                return
            for d in details:
                if not d["ok"]:
                    continue
                wechat_target = d.get("wechat_target") or os.getenv("DEFAULT_WECHAT_TARGET")
                if not wechat_target:
                    continue
                msg = d.get("message", "")
                if not msg:
                    continue
                r = await send_weixin_direct(
                    token=token,
                    chat_id=wechat_target,
                    message=msg,
                    extra={"account_id": account_id},
                )
                if r.get("success"):
                    print(f"  ✅ {d['tenant_id']} / {d['track_id']} → 微信 {wechat_target}", flush=True)
                else:
                    print(f"  ❌ {d['tenant_id']} / {d['track_id']}: {r.get('error')}", flush=True)

        asyncio.run(send_all())
        print(f"[推送] 完成: 成功{total}份 / 失败{failed}份", flush=True)

    finally:
        session.close()


if __name__ == "__main__":
    push_today_reports()
