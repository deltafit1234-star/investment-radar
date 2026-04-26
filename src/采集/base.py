"""
数据采集器基类
所有具体数据采集器都应继承此类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger


@dataclass
class CollectorResult:
    """采集结果"""
    source_id: str
    success: bool
    data: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    total_count: int = 0
    
    def __post_init__(self):
        self.total_count = len(self.data)


class BaseCollector(ABC):
    """数据采集器基类"""
    
    def __init__(self, source_config: Dict[str, Any]):
        """
        初始化采集器
        
        Args:
            source_config: 数据源配置，来自赛道YAML配置
        """
        self.source_id = source_config.get("source_id", "")
        self.name = source_config.get("name", self.source_id)
        self.config = source_config
        self.provider = source_config.get("provider", "")
        self.endpoint = source_config.get("endpoint", "")
        self.params = source_config.get("params", {})
        self.enabled = source_config.get("enabled", True)
        
        logger.info(f"采集器初始化: {self.source_id} ({self.name})")
    
    @abstractmethod
    def fetch(self) -> CollectorResult:
        """
        执行数据采集
        子类必须实现此方法
        
        Returns:
            CollectorResult: 采集结果
        """
        pass
    
    def validate_config(self) -> bool:
        """验证配置是否正确"""
        if not self.source_id:
            logger.error(f"采集器配置错误: source_id 为空")
            return False
        if not self.enabled:
            logger.warning(f"采集器未启用: {self.source_id}")
            return False
        return True
    
    def run(self) -> CollectorResult:
        """
        运行采集器
        包含错误处理和日志记录
        """
        if not self.validate_config():
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error="配置验证失败"
            )
        
        logger.info(f"开始采集: {self.source_id}")
        start_time = datetime.utcnow()
        
        try:
            result = self.fetch()
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"采集完成: {self.source_id} - "
                f"成功:{result.success} - "
                f"数据:{result.total_count}条 - "
                f"耗时:{elapsed:.2f}秒"
            )
            return result
        except Exception as e:
            logger.error(f"采集异常: {self.source_id} - {str(e)}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=str(e)
            )
    
    def _build_params(self, **overrides) -> Dict[str, Any]:
        """
        构建请求参数
        合并默认配置和覆盖参数
        """
        params = self.params.copy()
        params.update(overrides)
        return params
