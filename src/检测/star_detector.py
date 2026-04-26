"""
Star 异常检测器
检测 GitHub 项目 Star 数量的异常增长
"""

from typing import Dict, Any, Optional, List
from loguru import logger


class StarSurgeDetector:
    """Star 异常增长检测器"""
    
    def __init__(self, thresholds: Optional[Dict[str, float]] = None):
        """
        初始化检测器
        
        Args:
            thresholds: 阈值配置 {"high": 0.5, "medium": 0.3, "low": 0.1}
        """
        self.thresholds = thresholds or {
            "high": 0.5,    # 50% 增长
            "medium": 0.3,  # 30% 增长
            "low": 0.1,     # 10% 增长
        }
        self.min_stars = 1000      # 最低基数
        self.min_growth = 100      # 最低增长绝对值
    
    def detect(self, repo_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        检测 Star 异常
        
        Args:
            repo_data: 包含 stars 和 stars_previous (或 stars_history) 的字典
            
        Returns:
            检测结果字典，无异常时返回 None
        """
        stars = repo_data.get("stars", 0)
        stars_previous = repo_data.get("stars_previous")
        
        # 如果没有 previous 数据，跳过检测
        if stars_previous is None:
            logger.debug(f"无历史数据，跳过检测: {repo_data.get('full_name', 'unknown')}")
            return None
        
        # 过滤小项目
        if stars < self.min_stars:
            return None
        
        # 计算增长率
        growth_rate = (stars - stars_previous) / stars_previous if stars_previous > 0 else 0
        
        # 过滤绝对增长量
        absolute_growth = stars - stars_previous
        if absolute_growth < self.min_growth:
            return None
        
        # 判断优先级
        priority = self._classify_priority(growth_rate)
        
        if priority:
            return {
                "type": "star_surge",
                "full_name": repo_data.get("full_name"),
                "stars": stars,
                "stars_previous": stars_previous,
                "growth_rate": growth_rate,
                "absolute_growth": absolute_growth,
                "priority": priority,
                "message": self._build_message(repo_data, growth_rate, priority)
            }
        
        return None
    
    def _classify_priority(self, growth_rate: float) -> Optional[str]:
        """根据增长率分类优先级"""
        if growth_rate >= self.thresholds["high"]:
            return "high"
        elif growth_rate >= self.thresholds["medium"]:
            return "medium"
        elif growth_rate >= self.thresholds["low"]:
            return "low"
        return None
    
    def _build_message(self, repo_data: Dict, growth_rate: float, priority: str) -> str:
        """构建告警消息"""
        name = repo_data.get("full_name", "unknown")
        stars = repo_data.get("stars", 0)
        growth_pct = f"{growth_rate * 100:.1f}%"
        
        return f"Star 增长 {growth_pct} ({stars} stars) - {name}"
    
    def batch_detect(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量检测
        
        Args:
            repos: 仓库数据列表
            
        Returns:
            告警列表
        """
        alerts = []
        for repo in repos:
            alert = self.detect(repo)
            if alert:
                alerts.append(alert)
        
        logger.info(f"批量检测完成: {len(repos)} 个项目, {len(alerts)} 个告警")
        return alerts
