"""
微信推送模块
"""

from typing import Optional
from loguru import logger


class WechatNotifier:
    """微信通知器"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        初始化微信通知器
        
        Args:
            webhook_url: 企业微信 webhook 地址（未来使用）
        """
        self.webhook_url = webhook_url
        logger.info("微信通知器初始化完成")
    
    def send_message(self, content: str, mentioned_list: Optional[list] = None) -> bool:
        """
        发送微信消息

        Args:
            content: 消息内容
            mentioned_list: 需要 @ 的用户列表

        Returns:
            是否发送成功
        """
        # 输出到 stdout，供 Hermes cron 捕获并通过 send_message 发送
        print(f"[WECHAT_MESSAGE_START]\n{content}\n[WECHAT_MESSAGE_END]")
        logger.info(f"微信消息已输出到 stdout（由 Hermes cron 捕获推送）: {content[:50]}...")
        return True
    
    def send_test_message(self, message: str) -> bool:
        """发送测试消息"""
        logger.info("发送测试消息...")
        return self.send_message(message)
    
    def format_signal_message(self, signal: dict) -> str:
        """
        格式化信号消息

        Args:
            signal: 信号字典

        Returns:
            格式化后的消息字符串
        """
        priority_emoji = {
            "high": "🚨",
            "medium": "⚡",
            "low": "📊"
        }

        emoji = priority_emoji.get(signal.get("priority", "low"), "📊")
        signal_type = signal.get("type", "unknown")

        # 兼容不同信号类型的字段映射
        if signal_type == "star_surge":
            title = signal.get("full_name", "")
            summary = signal.get("summary", f"Star {signal.get('stars', 0)}")
        elif signal_type == "paper_burst":
            title = f"相关领域新增 {signal.get('count', 0)} 篇论文"
            summary = signal.get("summary", "")
        else:
            title = signal.get("title", signal.get("full_name", ""))
            summary = signal.get("content", signal.get("summary", ""))

        meaning = signal.get("meaning", "")

        lines = [
            f"{emoji} [{signal_type.upper()}] {title}",
            "",
        ]

        if summary:
            lines.append(summary)

        if meaning:
            lines.append("")
            lines.append(f"💡 含义: {meaning}")

        return "\n".join(lines)
