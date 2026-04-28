"""
飞书推送模块（预留接口）
"""

from typing import Optional
from loguru import logger


class FeishuNotifier:
    """飞书通知器（预留，尚未实现）"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    def send_message(self, content: str, target: Optional[str] = None) -> bool:
        """
        发送飞书消息。

        Args:
            content: 消息内容
            target: 飞书 webhook URL 或群 ID
        """
        logger.warning("飞书推送尚未实现，当前为预留接口")
        # TODO(FUTURE): 实现飞书 webhook 推送
        # payload = {"msg_type": "text", "content": {"text": content}}
        # response = requests.post(self.webhook_url or target, json=payload)
        return False

    def format_signal_message(self, signal: dict) -> str:
        """格式化信号消息（与微信保持一致格式）"""
        # TODO(FUTURE): 实现飞书特定格式化
        return f"[飞书] {signal.get('title', signal.get('full_name', ''))}"
