"""
邮件推送模块（预留接口）
"""

from typing import Optional
from loguru import logger


class EmailNotifier:
    """邮件通知器（预留，尚未实现）"""

    def __init__(self, smtp_host: str = None, smtp_port: int = 587,
                 username: str = None, password: str = None):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    def send_message(self, content: str, to_email: str = None, subject: str = "投资雷达 - 信号通知", **kwargs) -> bool:
        """
        发送邮件。

        Args:
            content: 邮件正文
            to_email: 收件人邮箱（也接受 target=kwargs 形式）
            subject: 邮件主题
            **kwargs: 兼容 router 的通用参数（target 等）
        """
        # 兼容 router 传入的 target 参数
        target = kwargs.get("target", to_email)
        if not target:
            logger.warning("[邮件推送] 无收件人地址，跳过")
            return False
        logger.warning(f"[邮件推送] 收件人: {target}, 内容: {content[:50]}...")
        # TODO(FUTURE): 实现 SMTP 邮件发送
        # import smtplib
        # from email.mime.text import MIMEText
        # msg = MIMEText(content, 'plain', 'utf-8')
        # msg['Subject'] = subject
        # msg['To'] = to_email
        # with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
        #     server.starttls()
        #     server.login(self.username, self.password)
        #     server.send_message(msg)
        return False

    def format_signal_message(self, signal: dict) -> str:
        """格式化信号消息"""
        # TODO(FUTURE): 实现邮件特定格式化
        return f"{signal.get('title', signal.get('full_name', ''))}"
