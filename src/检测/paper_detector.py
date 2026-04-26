"""
Paper Burst 检测器
检测某领域论文数量的异常激增
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger


class PaperBurstDetector:
    """论文激增检测器"""

    def __init__(
        self,
        thresholds: Optional[Dict[str, int]] = None,
        keywords: Optional[List[str]] = None,
    ):
        """
        初始化检测器

        Args:
            thresholds: 阈值配置 {"high": 20, "medium": 10}
            keywords: 关键词列表，用于过滤相关论文
        """
        self.thresholds = thresholds or {
            "high": 20,    # 篇/天，高优先级
            "medium": 10,  # 篇/天，中优先级
        }
        self.keywords = keywords or [
            "transformer", "attention", "LLM", "language model",
            "GPT", "BERT", "multimodal", "foundation model",
        ]

    def detect(self, paper_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        检测论文激增

        Args:
            paper_data: 包含以下字段的字典:
                - papers: 论文列表（今日/本周）
                - previous_papers: 对比期的论文列表（可选）
                - count: 论文数量
                - count_previous: 对比期数量（可选）

        Returns:
            检测结果字典，无异常时返回 None
        """
        papers = paper_data.get("papers", [])
        count = paper_data.get("count", len(papers))
        count_previous = paper_data.get("count_previous")

        # 无数据
        if count == 0:
            return None

        # 计算增长率（如果有历史数据）
        growth_rate = None
        if count_previous and count_previous > 0:
            growth_rate = (count - count_previous) / count_previous

        # 判断优先级
        priority = self._classify_priority(count, growth_rate)

        if priority:
            # 关键词匹配
            matched_papers = self._filter_by_keywords(papers)
            top_papers = matched_papers[:5]  # 取前5篇

            return {
                "type": "paper_burst",
                "count": count,
                "count_previous": count_previous,
                "growth_rate": growth_rate,
                "matched_count": len(matched_papers),
                "priority": priority,
                "top_papers": top_papers,
                "message": self._build_message(count, count_previous, priority),
            }

        return None

    def _classify_priority(self, count: int, growth_rate: Optional[float]) -> Optional[str]:
        """根据论文数量和增长率分类优先级"""
        # 直接按阈值判断
        if count >= self.thresholds["high"]:
            return "high"
        elif count >= self.thresholds["medium"]:
            return "medium"
        return None

    def _filter_by_keywords(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按关键词过滤论文"""
        if not self.keywords:
            return papers

        filtered = []
        for paper in papers:
            title = paper.get("title", "").lower()
            summary = paper.get("summary", "").lower()

            for kw in self.keywords:
                if kw.lower() in title or kw.lower() in summary:
                    filtered.append(paper)
                    break

        return filtered

    def _build_message(
        self, count: int, count_previous: Optional[int], priority: str
    ) -> str:
        """构建告警消息"""
        base = f"相关领域新增 {count} 篇论文"
        if count_previous:
            base += f"（对比期: {count_previous} 篇）"
        return base

    def batch_detect(self, paper_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量检测

        Args:
            paper_groups: 论文分组列表，每个分组有自己的 papers/count

        Returns:
            告警列表
        """
        alerts = []
        for group in paper_groups:
            alert = self.detect(group)
            if alert:
                alerts.append(alert)

        logger.info(f"批量论文检测完成: {len(paper_groups)} 个分组, {len(alerts)} 个告警")
        return alerts
