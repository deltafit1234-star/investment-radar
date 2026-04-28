"""
arXiv RSS 采集器 — 替代方案
当 arXiv API 触发 429 限流时，使用 RSS feeds 作为备用采集途径
RSS feeds 完全不限流，数据略有延迟（约几小时）
"""

import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger

from .base import BaseCollector, CollectorResult


class ArxivRssCollector(BaseCollector):
    """
    arXiv RSS Feed 采集器

    优点：
    - 完全不限流
    - 无需处理 429 问题
    - 无需 API key

    缺点：
    - 数据有轻微延迟（RSS 更新频率决定，通常几小时）
    - 无法自定义复杂查询，只能按分类获取

    适用场景：
    - 作为 arxiv_api 的备用采集器
    - 当 API 限流时的降级方案
    """

    # arXiv RSS feeds 按分类
    RSS_CATEGORIES = {
        "cs.AI": "https://arxiv.org/rss/cs.AI",
        "cs.CL": "https://arxiv.org/rss/cs.CL",
        "cs.LG": "https://arxiv.org/rss/cs.LG",
        "cs.CV": "https://arxiv.org/rss/cs.CV",
        "cs.NE": "https://arxiv.org/rss/cs.NE",
        "cs.RO": "https://arxiv.org/rss/cs.RO",  # Robotics
        "cs.AI": "https://arxiv.org/rss/cs.AI",
    }

    # 赛道配置 → RSS 分类映射
    TRACK_CATEGORIES = {
        "arxiv_cs_ai": ["cs.AI", "cs.CL", "cs.LG"],
        "arxiv_cs_cv": ["cs.CV"],
        "arxiv_cs_ne": ["cs.NE"],
        "arxiv_robotics": ["cs.RO"],
    }

    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.categories = self._resolve_categories()
        self.max_per_category = self.params.get("max_per_category", 30)

    def _resolve_categories(self) -> List[str]:
        """根据 source_id 解析对应的 RSS 分类列表"""
        # 如果显式配置了 categories，优先使用
        if "categories" in self.params:
            return self.params["categories"]

        # 按 source_id 映射
        return self.TRACK_CATEGORIES.get(
            self.source_id,
            ["cs.AI", "cs.CL"]  # 默认
        )

    def fetch(self) -> CollectorResult:
        """从多个 RSS feed 获取论文"""
        all_papers = []
        errors = []

        for category in self.categories:
            feed_url = self._get_feed_url(category)
            logger.debug(f"arXiv RSS 获取: {category} → {feed_url}")

            try:
                papers = self._fetch_single_feed(feed_url, category)
                all_papers.extend(papers)
                logger.info(f"arXiv RSS {category}: 获取 {len(papers)} 篇")
            except Exception as e:
                errors.append(f"{category}: {str(e)}")
                logger.warning(f"arXiv RSS {category} 失败: {e}")

        if not all_papers and errors:
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                data=[],
                error=f"所有 RSS feed 失败: {'; '.join(errors)}"
            )

        # 按发布时间排序（最新优先）
        all_papers.sort(
            key=lambda p: p.get("published_datetime", ""),
            reverse=True
        )

        logger.info(f"arXiv RSS 总计获取 {len(all_papers)} 篇论文")

        return CollectorResult(
            source_id=self.source_id,
            success=True,
            data=all_papers,
        )

    def _get_feed_url(self, category: str) -> str:
        """获取分类的 RSS URL"""
        # 直接支持自定义 URL
        if category.startswith("http"):
            return category
        return self.RSS_CATEGORIES.get(category, f"https://arxiv.org/rss/{category}")

    def _fetch_single_feed(self, feed_url: str, category: str) -> List[Dict[str, Any]]:
        """获取单个 RSS feed 并解析"""
        response = requests.get(feed_url, timeout=30)
        response.raise_for_status()

        return self._parse_rss_feed(response.text, category)

    def _parse_rss_feed(self, xml_text: str, category: str) -> List[Dict[str, Any]]:
        """
        解析 RSS/Atom feed

        arXiv RSS 格式示例：
        <?xml version="1.0" encoding="utf-8"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                 xmlns:atom="http://www.w3.org/2005/Atom"
                 xmlns:arxiv="http://arxiv.org/rss/schema/2024/arxiv.xsd">
          <item>
            <title>...</title>
            <link>https://arxiv.org/abs/2501.XXXXX</link>
            <description>...</description>
            <author>...</author>
            <category>cs.AI</category>
            <pubDate>Mon, 01 Jan 2025 00:00:00 +0000</pubDate>
            <guid isPermaLink="false">urn:arxiv:2501.XXXXX</guid>
          </item>
        </rdf:RDF>
        """
        papers = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"RSS XML 解析失败: {e}")
            return []

        # 尝试两种命名空间
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        }

        # 尝试找到 items（兼容 RSS 和 Atom 格式）
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//atom:entry", ns)
        if not items:
            # 尝试无命名空间
            items = root.findall(".//item") or root.findall(".//entry")

        for item in items:
            paper = self._parse_item(item, category, ns)
            if paper:
                papers.append(paper)

        return papers

    def _parse_item(
        self,
        item,
        category: str,
        ns: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """解析单个 item/entry"""
        try:
            # 标题
            title_el = item.find("title")
            title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

            # 链接
            link_el = item.find("link")
            link = ""
            if link_el is not None:
                link = link_el.text.strip() if link_el.text else ""
                # Atom 格式的 link 可能没有 text
                if not link:
                    link = link_el.get("href", "")
            if not link:
                link_el_href = item.find("atom:link[@href]", ns)
                if link_el_href is not None:
                    link = link_el_href.get("href", "")

            # 摘要/描述
            desc_el = item.find("description")
            summary = ""
            if desc_el is not None and desc_el.text:
                summary = desc_el.text.strip()
                # RSS 的 description 是 HTML，需要简单清理
                import re
                summary = re.sub(r"<[^>]+>", "", summary)
                summary = summary.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            else:
                # 尝试 Atom summary
                sum_el = item.find("atom:summary", ns)
                if sum_el is not None and sum_el.text:
                    summary = sum_el.text.strip()

            # 作者
            author_el = item.find("author")
            authors = []
            if author_el is not None and author_el.text:
                authors = [author_el.text.strip()]
            else:
                # 尝试多个 author 元素
                for a in item.findall("atom:author", ns):
                    name = a.find("atom:name", ns)
                    if name is not None and name.text:
                        authors.append(name.text.strip())

            # arXiv ID 从 link 或 guid 提取
            arxiv_id = self._extract_arxiv_id(link, item)

            # 发布日期
            published_str = ""
            pub_date_el = item.find("pubDate")
            if pub_date_el is not None and pub_date_el.text:
                published_str = self._parse_rss_date(pub_date_el.text)
            else:
                # 尝试 Atom published
                pub_el = item.find("atom:published", ns)
                if pub_el is not None and pub_el.text:
                    published_str = pub_el.text.text[:10] if pub_el.text else ""

            # 分类
            categories = []
            for cat_el in item.findall("category"):
                term = cat_el.text
                if term:
                    categories.append(term)
            if not categories and category:
                categories = [category]

            # arXiv URL
            arxiv_url = link if "arxiv.org" in link else f"https://arxiv.org/abs/{arxiv_id}"

            # 截断摘要
            if len(summary) > 500:
                summary = summary[:500] + "..."

            paper = {
                "external_id": arxiv_id,
                "arxiv_url": arxiv_url,
                "title": title,
                "summary": summary,
                "authors": authors,
                "author_count": len(authors),
                "published": published_str,
                "published_datetime": published_str + "T00:00:00" if published_str else "",
                "updated": None,
                "categories": categories,
                "comment": "",
                "doi": "",
                "fetched_at": datetime.utcnow().isoformat(),
            }
            return paper

        except Exception as e:
            logger.warning(f"解析 RSS item 失败: {e}")
            return None

    def _extract_arxiv_id(self, link: str, item) -> str:
        """从 URL 或 guid 提取 arXiv ID"""
        import re

        # 从链接提取
        if link:
            match = re.search(r"abs/([0-9]+\.[0-9]+)", link)
            if match:
                return match.group(1)

        # 从 guid 提取
        guid_el = item.find("guid")
        if guid_el is not None and guid_el.text:
            match = re.search(r"([0-9]+\.[0-9]+)", guid_el.text)
            if match:
                return match.group(1)

        return ""

    def _parse_rss_date(self, date_str: str) -> str:
        """
        解析 RSS 日期格式
        格式示例: "Mon, 01 Jan 2025 00:00:00 +0000"
        """
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            # 尝试手动解析
            months = {
                "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
            }
            parts = date_str.split()
            if len(parts) >= 4:
                day = parts[1].zfill(2)
                month = months.get(parts[2], "01")
                year = parts[3]
                return f"{year}-{month}-{day}"
            return ""


class ArxivHybridCollector(ArxivRssCollector):
    """
    混合采集器 — 优先使用 API，失败时降级到 RSS

    工作流程：
    1. 先尝试 ArxivCollector（API 模式）
    2. 如果触发 429 或失败，切换到 ArxivRssCollector（RSS 模式）
    3. 最终返回 API 结果（如果成功）或 RSS 结果（降级）

    用途：
    - 替换现有的 ArxivCollector
    - 在 cron 中自动处理限流，无需人工干预
    """

    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        # 内部两个采集器
        self._api_collector = None  # 延迟初始化

    def _get_api_collector(self):
        """延迟加载 API 采集器"""
        if self._api_collector is None:
            from .arxiv import ArxivCollector
            self._api_collector = ArxivCollector(self.config)
        return self._api_collector

    def fetch(self) -> CollectorResult:
        """
        混合采集策略：
        1. 尝试 API（优先，数据更完整）
        2. 失败则降级到 RSS
        """
        # 尝试 API 模式
        api_result = self._try_api_fetch()

        if api_result.success and api_result.total_count > 0:
            logger.info(
                f"arXiv API 成功: {api_result.total_count} 篇论文"
            )
            return api_result

        # API 失败或无数据，降级到 RSS
        logger.warning(
            f"arXiv API 不可用（{api_result.error or '0 篇论文'}），"
            f"降级到 RSS 模式"
        )
        rss_result = super().fetch()
        rss_result.error = (
            f"[RSS降级] API失败: {api_result.error}; "
            f"RSS获取: {rss_result.total_count} 篇"
        )
        return rss_result

    def _try_api_fetch(self) -> CollectorResult:
        """尝试一次 API 采集（不复用重试逻辑）"""
        try:
            from .arxiv import ArxivCollector
            collector = ArxivCollector(self.config)
            return collector.fetch()
        except Exception as e:
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"API采集异常: {str(e)}"
            )
