#!/usr/bin/env python3
"""
投资雷达 - 每日推送脚本（供 Hermes cron 调用）
流程：生成日报PDF → 发送微信
"""
import sys, os, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

def main():
    tenant_id = os.environ.get("SYSTEM_TENANT_ID", "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat")

    # 1. 生成日报
    print("[日报推送] 开始生成日报...", flush=True)
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "scripts/gen_daily_reports.py"),
         "--tenant", tenant_id, "--hours", "24"],
        capture_output=True, text=True, timeout=120,
        cwd=str(BASE_DIR)
    )
    print(result.stdout, flush=True)
    if result.returncode != 0:
        print("STDERR:", result.stderr[:500], flush=True)

    # 2. 提取PDF路径
    pdf_path = None
    for line in result.stdout.splitlines():
        if line.startswith("OUTPUT:"):
            pdf_path = line.split(":", 1)[1].strip()
            break

    if not pdf_path or not Path(pdf_path).exists():
        print(f"[日报推送] 生成失败或PDF不存在: {pdf_path}", flush=True)
        sys.exit(1)

    print(f"[日报推送] PDF已生成: {pdf_path}", flush=True)

    # 3. 打印WECHAT_MESSAGE_START/END供Hermes捕获
    file_size = Path(pdf_path).stat().st_size
    msg = f"""📊 未来产业情报 {Path(pdf_path).stem.replace('未来产业日报-', '')}

今日信号已生成，共 {file_size//1024}KB
PDF路径: {pdf_path}

[WECHAT_FILE]{pdf_path}[/WECHAT_FILE]
[WECHAT_MESSAGE_END]"""
    msg_start = msg.replace("\n[WECHAT_FILE]", "\n[WECHAT_FILE]").replace("[WECHAT_MESSAGE_END]\n[WECHAT_FILE]", "[WECHAT_FILE]")
    # Find and fix the structure
    msg = f"""📊 未来产业情报 {Path(pdf_path).stem.replace('未来产业日报-', '')}

今日信号已生成，PDF {file_size//1024}KB

[WECHAT_MESSAGE_START]
📎 未来产业日报-{Path(pdf_path).stem.replace('未来产业日报-', '')}.pdf
附件发送PDF文件
[WECHAT_FILE]{pdf_path}[/WECHAT_FILE]
[WECHAT_MESSAGE_END]"""

    print(msg, flush=True)

if __name__ == "__main__":
    main()
