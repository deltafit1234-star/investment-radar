"""
Hacker News Algolia 搜索采集器（Phase 2 ProtoType）
使用 HN 官方 Algolia Search API，免费、快速，支持关键词搜索

signal_type: hackernews_hot
API: https://hn.algolia.com/api/v1/search?query=keyword
"""

import requests
import time
from typing import Optional, List
from loguru import logger


class HackerNewsCollector:
    """Hacker News Algolia 关键词搜索（替代 Firebase 逐条抓取，速度快 10 倍）"""

    signal_type = "hackernews_hot"
    algolia_url = "https://hn.algolia.com/api/v1/search"
    session = None  # 类级别 session 复用

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.timeout = 10
        self.max_results = 10  # 每次最多返回条数

    def collect(self, keyword: str, max_results: int = 20) -> dict:
        """
        使用 Algolia HN Search API 进行关键词搜索
        一个请求返回所有结果，无需逐条抓取
        """
        try:
            # Algolia HN Search API - 支持 tags=story 过滤
            params = {
                "query": keyword,
                "tags": "story",
                "hitsPerPage": min(max_results, self.max_results),
            }
            resp = requests.get(
                self.algolia_url,
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])

            results = []
            for hit in hits:
                results.append({
                    "id": hit.get("objectID"),
                    "title": hit.get("title", ""),
                    "url": hit.get("url", "") or hit.get("story_url", ""),
                    "score": hit.get("points", 0),
                    "by": hit.get("author", ""),
                    "time": hit.get("created_at", "")[:19].replace("T", " "),  # ISO -> YYYY-MM-DD HH:MM:SS
                    "descendants": hit.get("num_comments", 0),
                    "text": hit.get("story_text", "")[:300] if hit.get("story_text") else "",
                    "keyword": keyword,
                    "signal_type": self.signal_type,
                })

            return {
                "success": True,
                "data": results,
                "total_count": len(results),
                "error": None,
            }

        except requests.exceptions.Timeout:
            logger.warning(f"  Hacker News 超时: {keyword}")
            return {"success": False, "data": [], "total_count": 0, "error": "timeout"}
        except requests.exceptions.RequestException as e:
            logger.warning(f"  Hacker News 请求失败: {e}")
            return {"success": False, "data": [], "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.exception(f"  Hacker News 异常: {e}")
            return {"success": False, "data": [], "total_count": 0, "error": str(e)}

    def run(self, keywords: list = None) -> dict:
        """批量关键词搜索"""
        if keywords is None:
            keywords = []
        all_results = []
        for kw in keywords:
            result = self.collect(kw)
            if result["success"]:
                all_results.extend(result["data"])
        return {
            "success": True,
            "data": all_results,
            "total_count": len(all_results),
            "error": None,
        }


def create_collector(config: dict = None) -> HackerNewsCollector:
    return HackerNewsCollector(config)
