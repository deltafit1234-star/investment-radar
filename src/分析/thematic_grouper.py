"""专题分组模块 - 将检测到的信号按主题/赛道分组
用于关联分析前的信号组织
"""

from typing import List, Dict, Any
from collections import defaultdict
from loguru import logger


class ThematicGrouper:
    """信号专题分组器"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    def group(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将信号按主题分组，返回带 group_id 的信号列表"""
        if not signals:
            return []

        # 按信号类型分组
        type_groups = defaultdict(list)
        for sig in signals:
            sig_type = sig.get("type", "unknown")
            type_groups[sig_type].append(sig)

        grouped_signals = []

        for sig in signals:
            sig = sig.copy()
            sig_type = sig.get("type", "unknown")

            # 根据类型分配 group_id
            if sig_type == "star_surge":
                sig["group_id"] = self._extract_repo_topic(sig)
            elif sig_type == "paper_burst":
                sig["group_id"] = f"paper_{sig.get('domain', 'general')}"
            elif sig_type == "funding_news":
                sig["group_id"] = self._extract_company_keyword(sig)
            elif sig_type == "model_news":
                sig["group_id"] = self._extract_model_topic(sig)
            else:
                sig["group_id"] = sig_type

            grouped_signals.append(sig)

        logger.info(f"  专题分组完成: {len(grouped_signals)} 个信号")
        return grouped_signals

    def _extract_repo_topic(self, sig: Dict) -> str:
        """从 star_surge 信号提取主题"""
        full_name = sig.get("full_name", "")
        description = sig.get("description", "")
        name = sig.get("name", "")

        # 优先用 repo 名 + description 关键词判断主题
        combined = f"{name} {description}".lower()

        topics = []
        if any(k in combined for k in ["llm", "language model", "gpt", "claude", "openai"]):
            topics.append("llm")
        if any(k in combined for k in ["image", "vision", "diffusion", "stable", "midjourney"]):
            topics.append("image_gen")
        if any(k in combined for k in ["agent", "autonomous", "task"]):
            topics.append("agent")
        if any(k in combined for k in ["video", "sora", "generate"]):
            topics.append("video_gen")
        if any(k in combined for k in ["robot", "reinforcement", "robotics"]):
            topics.append("robotics")

        if topics:
            return f"star_{topics[0]}"
        return f"star_general"

    def _extract_company_keyword(self, sig: Dict) -> str:
        """从融资新闻提取公司/关键词"""
        title = sig.get("full_name", "") or sig.get("title", "")
        content = sig.get("content", "")

        text = f"{title} {content}".lower()

        # 提取公司名中包含的技术关键词
        if "大模型" in text or "llm" in text:
            return "funding_llm"
        if "机器人" in text or "robot" in text:
            return "funding_robot"
        if "芯片" in text or "半导体" in text:
            return "funding_chip"
        return "funding_general"

    def _extract_model_topic(self, sig: Dict) -> str:
        """从模型新闻提取主题"""
        title = sig.get("full_name", "") or sig.get("title", "")
        content = sig.get("content", "")

        text = f"{title} {content}".lower()

        if any(k in text for k in ["多模态", "multimodal", "vision"]):
            return "model_multimodal"
        if any(k in text for k in ["开源", "open", "llama", "mistral"]):
            return "model_open"
        if any(k in text for k in ["视频", "video", "sora"]):
            return "model_video"
        return "model_general"


def run_thematic_grouping(signals: List[Dict[str, Any]], config, track_id: str = "ai_llm") -> List[Dict[str, Any]]:
    """专题分组入口函数"""
    logger.info("[专题分组] 信号分组处理...")
    try:
        grouper = ThematicGrouper(config=config)
        grouped = grouper.group(signals)

        group_ids = set(s.get("group_id", "unknown") for s in grouped)
        logger.info(f"  分组完成: {len(grouped)} 个信号, {len(group_ids)} 个主题组")

        return grouped
    except Exception as e:
        logger.warning(f"  专题分组异常: {e}，跳过分组")
        return signals