"""
Hacker News API 热点项目采集器（Prototype）
使用官方免费 Firebase API，无认证要求

signal_type: hackernews_hot
"""

import requests
import time
from typing import Optional
from loguru import logger


class HackerNewsCollector:
    """Hacker News 社区热点采集"""

    signal_type = "hackernews_hot"
    top_stories_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    item_url = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.timeout = 10
        self.max_stories = 30  # 每次取 Top 30

    def collect(self, keyword: str, max_results: int = 20) -> dict:
        """
        按关键词搜索 Hacker News 热点

        Args:
            keyword: 搜索关键词
            max_results: 最大结果数

        Returns:
            CollectionResult 格式 dict
        """
        try:
            # 获取 Top Stories IDs
            resp = requests.get(self.top_stories_url, timeout=self.timeout)
            resp.raise_for_status()
            story_ids = resp.json()[: self.max_stories]

            results = []
            keyword_lower = keyword.lower()

            for story_id in story_ids:
                try:
                    item_resp = requests.get(
                        self.item_url.format(id=story_id),
                        timeout=self.timeout,
                    )
                    if item_resp.status_code != 200:
                        continue
                    story = item_resp.json()

                    if not story or story.get("deleted") or story.get("dead"):
                        continue

                    story_type = story.get("type", "story")
                    if story_type != "story":
                        continue

                    title = story.get("title", "")
                    url = story.get("url", "")
                    text = story.get("text", "") or ""

                    # 关键词匹配（title + url + text）
                    match_text = (title + " " + url + " " + text).lower()
                    if keyword_lower not in match_text:
                        continue

                    # 转换为 YYYY-MM-DD HH:MM:SS
                    time_int = story.get("time", 0)
                    time_str = (
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_int))
                        if time_int
                        else ""
                    )

                    results.append({
                        "id": story.get("id"),
                        "title": title,
                        "url": url,
                        "score": story.get("score", 0),
                        "by": story.get("by", ""),
                        "time": time_str,
                        "descendants": story.get("descendants", 0),
                        "text": text[:300] if text else "",
                        "keyword": keyword,
                        "signal_type": self.signal_type,
                    })

                    if len(results) >= max_results:
                        break

                    # 避免请求过快
                    time.sleep(0.1)

                except Exception:
                    continue

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
