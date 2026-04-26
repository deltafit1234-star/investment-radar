"""
LLM 信号丰富化模块
使用 LLM 为原始信号补充上下文和含义解读
"""

from typing import Dict, Any, Optional
from loguru import logger


class SignalEnricher:
    """信号丰富化器"""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        """
        初始化信号丰富化器
        
        Args:
            llm_config: LLM 配置字典
        """
        self.config = llm_config or {}
        self.model = self.config.get("model", "gpt-4o-mini")
        self.max_tokens = self.config.get("max_tokens", 500)
        logger.info(f"信号丰富化器初始化: {self.model}")
    
    def enrich(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        丰富单个信号
        
        Args:
            signal: 原始信号字典
            
        Returns:
            丰富后的信号字典
        """
        signal_type = signal.get("type", "unknown")
        
        # 🚨 SHORTcut: 模拟 LLM 响应用于演示
        # TODO(FUTURE): 实现真实的 OpenAI API 调用
        enriched = signal.copy()
        
        if signal_type == "star_surge":
            enriched["summary"] = self._mock_summarize_star(signal)
            enriched["meaning"] = self._mock_interpret_star(signal)
        elif signal_type == "paper_burst":
            enriched["summary"] = self._mock_summarize_paper(signal)
            enriched["meaning"] = self._mock_interpret_paper(signal)
        else:
            enriched["summary"] = signal.get("content", "")[:200]
            enriched["meaning"] = "需人工判断"
        
        logger.debug(f"信号丰富化完成: {signal_type}")
        return enriched
    
    def batch_enrich(self, signals: list) -> list:
        """
        批量丰富信号
        
        Args:
            signals: 信号列表
            
        Returns:
            丰富后的信号列表
        """
        return [self.enrich(s) for s in signals]
    
    def _mock_summarize_star(self, signal: Dict) -> str:
        """模拟 Star 信号的总结"""
        name = signal.get("full_name", "")
        stars = signal.get("stars", 0)
        growth = signal.get("growth_rate", 0)
        return f"{name} 的 Star 数量达到 {stars}，较之前增长 {growth*100:.0f}%"
    
    def _mock_interpret_star(self, signal: Dict) -> str:
        """模拟 Star 信号的意义解读"""
        name = signal.get("full_name", "")
        growth = signal.get("growth_rate", 0)
        if growth > 0.5:
            return f"🔥 {name} 增长迅猛，可能代表新的技术趋势或应用方向，建议关注"
        elif growth > 0.3:
            return f"📈 {name} 增长较快，值得关注其发展动态"
        else:
            return f"📊 {name} 有一定增长，可持续观察"
    
    def _mock_summarize_paper(self, signal: Dict) -> str:
        """模拟论文信号的总结"""
        count = signal.get("count", 0)
        return f"相关领域新增论文 {count} 篇"
    
    def _mock_interpret_paper(self, signal: Dict) -> str:
        """模拟论文信号的意义解读"""
        return "论文数量激增可能代表技术突破或研究热点，建议关注"
