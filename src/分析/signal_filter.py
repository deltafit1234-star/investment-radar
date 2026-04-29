"""信号过滤器模块 - 在信号保存前进行质量过滤
过滤低质量/重复信号，提升推送质量
"""

from typing import List, Dict, Any, Set
from loguru import logger


class SignalFilter:
    """信号质量过滤器"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.min_priority = self.config.get("min_priority", "low")
        self.priority_order = ["low", "medium", "high"]

    def filter(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤低质量信号，返回过滤后的信号列表"""
        if not signals:
            return []

        original_count = len(signals)
        filtered = []

        # 去重：相同 title 保留优先级最高的
        seen_titles: Set[str] = set()

        for sig in signals:
            title = (sig.get("full_name") or sig.get("title") or "").strip()
            if not title:
                continue

            # title 去重（取前60字符作为key）
            title_key = title[:60].lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            # 优先级过滤：低于最低阈值则跳过
            priority = sig.get("priority", "low")
            if self._priority_lower_than(priority, self.min_priority):
                continue

            # 内容过滤：太短或太相似的跳过
            content = sig.get("content", "") or sig.get("description", "")
            if len(content) < 10 and sig.get("type") != "star_surge":
                continue

            filtered.append(sig)

        removed = original_count - len(filtered)
        if removed > 0:
            logger.info(f"  信号过滤: 移除 {removed} 个低质量/重复信号，剩余 {len(filtered)} 个")

        return filtered

    def _priority_lower_than(self, p1: str, p2: str) -> bool:
        """比较两个优先级，p1 < p2 返回 True"""
        order = self.priority_order
        try:
            return order.index(p1) < order.index(p2)
        except ValueError:
            return False


def run_signal_filter(signals: List[Dict[str, Any]], config, track_id: str = "ai_llm") -> List[Dict[str, Any]]:
    """信号过滤入口函数"""
    logger.info("[信号过滤] 质量过滤...")
    try:
        filter_cfg = {}
        # 从配置读取过滤规则
        try:
            from src.core.config import get_config
            cfg = get_config()
            filter_cfg = getattr(cfg, "filter_config", {})
        except Exception:
            pass

        signal_filter = SignalFilter(config=filter_cfg)
        filtered = signal_filter.filter(signals)

        logger.info(f"  信号过滤完成: {len(filtered)}/{len(signals)} 个信号通过")
        return filtered
    except Exception as e:
        logger.warning(f"  信号过滤异常: {e}，跳过过滤")
        return signals