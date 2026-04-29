"""
36kr 新闻采集器
通过 RSS Feed 采集 36kr 科技新闻
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger

from .base import BaseCollector, CollectorResult


class News36krCollector(BaseCollector):
    """36kr 新闻采集器"""

    RSS_URL = "https://36kr.com/feed"

    NS = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://36kr.com/",
        })

    def fetch(self) -> CollectorResult:
        """
        执行 36kr 新闻采集

        RSS Feed 结构:
        - channel > title: 频道标题
        - channel > item > title: 文章标题
        - channel > item > link: 文章链接
        - channel > item > description: 文章摘要
        - channel > item > pubDate: 发布时间
        - channel > item > category: 分类
        """
        try:
            response = self.session.get(self.RSS_URL, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"

            root = ET.fromstring(response.text)

            # 尝试 atom:link（有些 RSS 用 Atom 格式）
            channel = root.find("channel")
            if channel is None:
                # 纯 Atom 格式
                channel = root

            items = channel.findall("item")
            if not items:
                # Atom 格式的 entry
                items = root.findall(f".//atom:entry", self.NS)
                if not items:
                    items = root.findall(".//entry")

            normalized_data = []
            for item in items:
                entry = self._parse_item(item)
                if entry:
                    normalized_data.append(entry)

            logger.debug(f"36kr: 获取到 {len(normalized_data)} 条新闻")

            return CollectorResult(
                source_id=self.source_id,
                success=True,
                data=normalized_data
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"36kr 请求失败: {e}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"请求失败: {str(e)}"
            )
        except ET.ParseError as e:
            logger.error(f"36kr XML 解析失败: {e}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"XML解析失败: {str(e)}"
            )
        except Exception as e:
            logger.error(f"36kr 数据处理异常: {e}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"数据处理异常: {str(e)}"
            )

    def _parse_item(self, item) -> Optional[Dict[str, Any]]:
        """解析单个 RSS item 或 Atom entry"""
        try:
            # 标题
            title = self._get_tag_text(item, "title")
            if not title:
                return None

            # 链接
            link = self._get_tag_text(item, "link")
            if not link:
                # Atom 格式的 link
                link_el = item.find("link")
                if link_el is not None:
                    link = link_el.text or link_el.get("href", "")

            # 描述/摘要
            description = (
                self._get_tag_text(item, "description") or
                self._get_tag_text(item, "summary") or
                self._get_tag_text(item, "content:encoded") or
                ""
            )
            # 清理 HTML 标签
            description = self._strip_html(description)

            # 发布时间
            pub_date = (
                self._get_tag_text(item, "pubDate") or
                self._get_tag_text(item, "published") or
                self._get_tag_text(item, "updated") or
                ""
            )
            if pub_date:
                pub_date = self._parse_date(pub_date)

            # 分类
            categories = []
            for cat in item.findall("category"):
                if cat.text:
                    categories.append(cat.text)
            for cat in item.findall("atom:category", self.NS):
                if cat.text:
                    categories.append(cat.text)

            # 作者
            author = (
                self._get_tag_text(item, "author") or
                self._get_tag_text(item, "dc:creator") or
                ""
            )

            return {
                "title": title.strip(),
                "url": link.strip() if link else "",
                "description": description[:500] if description else "",
                "published_at": pub_date,
                "categories": categories,
                "author": author.strip() if author else "",
                "source": "36kr",
                "fetched_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.warning(f"解析 item 失败: {e}")
            return None

    def _get_tag_text(self, elem, tag: str) -> Optional[str]:
        """安全获取子元素的文本，处理命名空间"""
        # 先直接找
        el = elem.find(tag)
        if el is not None and el.text:
            return el.text

        # 尝试带命名空间
        for ns_prefix, ns_uri in self.NS.items():
            if ":" not in tag:
                continue
            local = tag.split(":", 1)[1]
            el = elem.find(f"{{{ns_uri}}}{local}")
            if el is not None and el.text:
                return el.text

        return None

    def _strip_html(self, text: str) -> str:
        """移除 HTML 标签"""
        if not text:
            return ""
        import re
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'")
        return text.strip()

    def _parse_date(self, date_str: str) -> str:
        """解析多种日期格式"""
        if not date_str:
            return ""

        import re
        date_str = date_str.strip()

        # RFC 822: "Wed, 02 Oct 2002 13:00:00 GMT"
        patterns = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in patterns:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.isoformat()
            except ValueError:
                continue

        # 手动解析 RFC 822
        try:
            # "Wed, 02 Oct 2002 13:00:00 GMT"
            m = re.match(r"\w+,\s+(\d+)\s+(\w+)\s+(\d+)\s+(\d+):(\d+):(\d+)", date_str)
            if m:
                months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
                d, mon, y, h, mi, s = m.groups()
                dt = datetime(int(y), months[mon], int(d), int(h), int(mi), int(s))
                return dt.isoformat()
        except Exception:
            pass

        return date_str
