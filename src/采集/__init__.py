"""
数据采集层
负责从各种数据源采集原始数据
"""

from .base import BaseCollector, CollectorResult
from .github import GitHubCollector

__all__ = ["BaseCollector", "CollectorResult", "GitHubCollector"]
