"""
GitHub 数据采集器
采集 GitHub Trending 和项目详情
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

from .base import BaseCollector, CollectorResult


class GitHubCollector(BaseCollector):
    """GitHub 数据采集器"""

    BASE_URL = "https://api.github.com"

    def __init__(self, source_config: Dict[str, Any], api_token: Optional[str] = None):
        super().__init__(source_config)

        # 从环境变量读取 token
        self.api_token = api_token or os.environ.get("GITHUB_TOKEN", "")

        if not self.api_token:
            logger.warning("GitHub API Token 未配置，GitHub API 请求可能受限（60 req/hr vs 5000 req/hr）")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Investment-Radar/1.0"
        })
        if self.api_token:
            self.session.headers["Authorization"] = f"token {self.api_token}"
    
    def fetch(self) -> CollectorResult:
        """
        执行 GitHub 数据采集
        
        根据 source_id 决定采集类型:
        - github_trending: 采集 Trending Repos
        """
        if self.source_id == "github_trending":
            return self._fetch_trending()
        else:
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"未知的 source_id: {self.source_id}"
            )
    
    def _fetch_trending(self) -> CollectorResult:
        """
        采集 GitHub Trending Repos
        
        使用 GitHub Search API
        """
        # 构建查询参数
        date_7d = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        params = self._build_params(
            q=f"language:python created:>{date_7d}",
            sort="stars",
            order="desc",
            per_page=25
        )
        
        url = f"{self.BASE_URL}/search/repositories"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            repos = data.get("items", [])
            
            # 转换为标准格式
            normalized_data = []
            for repo in repos:
                normalized_repo = {
                    "external_id": str(repo.get("id")),
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "description": repo.get("description"),
                    "url": repo.get("html_url"),
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language"),
                    "open_issues": repo.get("open_issues_count", 0),
                    "subscribers_count": repo.get("subscribers_count", 0),
                    "owner": {
                        "login": repo.get("owner", {}).get("login"),
                        "avatar_url": repo.get("owner", {}).get("avatar_url"),
                    },
                    "created_at": repo.get("created_at"),
                    "updated_at": repo.get("updated_at"),
                    "pushed_at": repo.get("pushed_at"),
                    "topics": repo.get("topics", []),
                    "fetched_at": datetime.utcnow().isoformat(),
                }
                normalized_data.append(normalized_repo)
            
            logger.debug(f"GitHub Trending: 获取到 {len(normalized_data)} 个仓库")  # 🔧 DEBUG: 调试日志
            
            return CollectorResult(
                source_id=self.source_id,
                success=True,
                data=normalized_data
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"GitHub API 请求失败: {e}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"API请求失败: {str(e)}"
            )
        except Exception as e:
            logger.error(f"GitHub 数据处理异常: {e}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"数据处理异常: {str(e)}"
            )
    
    def fetch_repo_details(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """
        获取单个仓库的详细信息
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            
        Returns:
            仓库详情字典
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            return {
                "name": data.get("name"),
                "full_name": data.get("full_name"),
                "description": data.get("description"),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "subscribers_count": data.get("subscribers_count", 0),
                "topics": data.get("topics", []),
                "language": data.get("language"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "pushed_at": data.get("pushed_at"),
                "fetched_at": datetime.utcnow().isoformat(),
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取仓库详情失败 {owner}/{repo}: {e}")
            return None
    
    def fetch_stars_history(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """
        获取仓库的 Star 历史
        
        注意: GitHub API 不直接提供 star 历史，
        此方法通过 Commit 活跃度间接推断
        
        Returns:
            包含 stars 计数的时间序列
        """
        # 🚨 SHORTcut: 使用简化的 Commit 活跃度代替真实 Star 历史
        # TODO(FUTURE): 接入专门提供 GitHub Stats 的第三方服务（如 gitstats, ghdata）
        
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/commits"
        
        try:
            response = self.session.get(
                url, 
                params={"per_page": 30},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # 简化实现：返回最近的 commit 记录作为活跃度指标
            history = []
            for i, commit in enumerate(data[:7]):  # 最近7次 commit
                history.append({
                    "date": commit.get("commit", {}).get("author", {}).get("date"),
                    "position": i,
                })
            
            return history
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取 Star 历史失败 {owner}/{repo}: {e}")
            return []
