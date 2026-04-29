"""
TechCrunch RSS 新闻采集器（Prototype）
使用 TechCrunch 免费 RSS Feed

signal_type: techcrunch_news
"""

import feedparser
import re
from datetime import datetime
from typing import Optional
from loguru import logger


class TechCrunchCollector:
    """TechCrunch RSS 国际科技新闻采集"""

    signal_type = "techcrunch_news"
    feed_url = "https://techcrunch.com/feed/"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.timeout = 15

    def collect(self, keyword: str, max_results: int = 20) -> dict:
        """
        搜索 TechCrunch 新闻

        Args:
            keyword: 搜索关键词
            max_results: 最大结果数

        Returns:
            CollectionResult 格式 dict
        """
        try:
            import requests
            resp = requests.get(self.feed_url, timeout=self.timeout)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            if not feed.entries:
                return {
                    "success": False,
                    "data": [],
                    "total_count": 0,
                    "error": "No entries found",
                }

            results = []
            keyword_lower = keyword.lower()

            for entry in feed.entries[:max_results]:
                try:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    link = entry.get("link", "")
                    published = entry.get("published", "")
                    author = entry.get("author", "")

                    # 从 summary 中提取纯文本（去除 HTML 标签）
                    plain_summary = re.sub(r"<[^>]+>", "", summary)

                    # 关键词匹配（title + summary + link）
                    text = (title + " " + plain_summary + " " + link).lower()
                    if keyword_lower not in text:
                        continue

                    # 提取分类标签
                    categories = [
                        tag.term
                        for tag in entry.get("tags", [])
                        if hasattr(tag, "term")
                    ]

                    # 提取缩略图
                    thumbnail = ""
                    enclosures = entry.get("enclosures", [])
                    if enclosures:
                        thumbnail = enclosures[0].get("href", "")
                    if not thumbnail:
                        media = entry.get("media_content", [])
                        if media:
                            thumbnail = media[0].get("url", "")

                    # 解析日期
                    parsed_date = ""
                    try:
                        dt = datetime(*entry.published_parsed[:6])
                        parsed_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        parsed_date = published

                    results.append({
                        "id": entry.get("id", link),
                        "title": title,
                        "link": link,
                        "summary": plain_summary[:300],
                        "published": parsed_date,
                        "author": author,
                        "categories": categories,
                        "thumbnail": thumbnail,
                        "keyword": keyword,
                        "signal_type": self.signal_type,
                    })
                except Exception:
                    continue

            return {
                "success": True,
                "data": results,
                "total_count": len(results),
                "error": None,
            }

        except Exception as e:
            logger.warning(f"  TechCrunch RSS 解析失败: {e}")
            return {
                "success": False,
                "data": [],
                "total_count": 0,
                "error": str(e),
            }

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


def create_collector(config: dict = None) -> TechCrunchCollector:
    return TechCrunchCollector(config)
