#!/usr/bin/env python3
"""
Hermes WeChat 推送脚本
由 Hermes cron 调用，提取 [WECHAT_MESSAGE_START]...[WECHAT_MESSAGE_END] 并发送
"""
import subprocess
import sys
import os
import re

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SCRIPT = os.path.join(BASE_DIR, "scripts", "run_local.py")

def main():
    # 读取 .env 中的 API key
    env = os.environ.copy()
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    # 运行 Pipeline
    result = subprocess.run(
        [sys.executable, RUN_SCRIPT],
        capture_output=True,
        text=True,
        timeout=300,
        env=env
    )

    # 提取 [WECHAT_MESSAGE_START]...[WECHAT_MESSAGE_END] 块
    stdout = result.stdout
    match = re.search(
        r"\[WECHAT_MESSAGE_START\](.*?)\[WECHAT_MESSAGE_END\]",
        stdout,
        re.DOTALL
    )

    if match:
        message = match.group(1).strip()
        print(f"[雷达推送] 捕获到消息，长度: {len(message)} 字符")
        print("--- 消息内容预览 ---")
        print(message[:200])
        print("--- end ---")
        # 返回消息供 Hermes send_message 使用
        print(f"[MESSAGE_FOR_HERMES]\n{message}\n[/MESSAGE_FOR_HERMES]")
    else:
        print("[雷达推送] 未捕获到微信消息块")
        print("stdout:", stdout[:500] if stdout else "(empty)")
        sys.exit(1)

if __name__ == "__main__":
    main()
