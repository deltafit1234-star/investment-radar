"""
arXiv 数据采集器
采集 AI/LLM 相关学术论文
"""

import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, Any, List
from loguru import logger

from .base import BaseCollector, CollectorResult


class ArxivCollector(BaseCollector):
    """arXiv 论文采集器"""

    BASE_URL = "http://export.arxiv.org/api/query"
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # 秒

    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.search_query = self.params.get("search_query", "cat:cs.AI")
        self.max_results = self.params.get("max_results", 50)

    def fetch(self) -> CollectorResult:
        """
        执行 arXiv 论文采集

        根据 source_id 决定采集范围:
        - arxiv_cs_ai: cs.AI + cs.CL (默认)
        - 其他: 使用配置的 search_query
        """
        if self.source_id == "arxiv_cs_ai":
            return self._fetch_cs_ai()
        else:
            return self._fetch_custom()

    def _fetch_cs_ai(self) -> CollectorResult:
        """采集 cs.AI 和 cs.CL 类别的最新论文"""
        return self._fetch_with_query(
            "cat:cs.AI OR cat:cs.CL",
            self.max_results
        )

    def _fetch_custom(self) -> CollectorResult:
        """使用自定义查询采集"""
        return self._fetch_with_query(
            self.search_query,
            self.max_results
        )

    def _fetch_with_query(self, query: str, max_results: int) -> CollectorResult:
        """通用的 arXiv 查询方法，带重试和限流处理"""
        import urllib.parse

        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": self.params.get("sortBy", "submittedDate"),
            "sortOrder": self.params.get("sortOrder", "descending"),
        }

        query_str = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{self.BASE_URL}?{query_str}"

        logger.debug(f"arXiv 查询: {url[:200]}...")

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()

                # 解析 XML
                papers = self._parse_atom_feed(response.text)

                logger.debug(f"arXiv: 获取到 {len(papers)} 篇论文")
                return CollectorResult(
                    source_id=self.source_id,
                    success=True,
                    data=papers,
                )

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                if status_code == 429:
                    # Rate limit — 等待后重试
                    wait_time = self.RETRY_DELAY * (attempt + 1)
                    logger.warning(f"arXiv 限流 (429)，等待 {wait_time}s 后重试 ({attempt+1}/{self.MAX_RETRIES})")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"arXiv HTTP 错误: {status_code} - {str(e)}")
                    return CollectorResult(
                        source_id=self.source_id,
                        success=False,
                        error=f"HTTP {status_code}: {str(e)}",
                    )

            except requests.exceptions.Timeout:
                logger.warning(f"arXiv 请求超时，重试 ({attempt+1}/{self.MAX_RETRIES})")
                time.sleep(self.RETRY_DELAY)
                continue

            except Exception as e:
                logger.error(f"arXiv 采集异常: {str(e)}")
                return CollectorResult(
                    source_id=self.source_id,
                    success=False,
                    error=f"采集异常: {str(e)}",
                )

        # 所有重试都失败
        return CollectorResult(
            source_id=self.source_id,
            success=False,
            error="arXiv 请求超时，已达最大重试次数",
        )

    def _parse_atom_feed(self, xml_text: str) -> List[Dict[str, Any]]:
        """解析 arXiv Atom Feed"""
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"arXiv XML 解析失败: {str(e)}")
            return []

        entries = root.findall("atom:entry", ns)
        papers = []

        for entry in entries:
            # Helper: 安全获取子元素文本
            def get_text(el_name, ns_map=ns):
                el = entry.find(f"atom:{el_name}", ns_map)
                return el.text.strip() if el is not None and el.text else ""

            # 解析作者
            author_els = entry.findall("atom:author/atom:name", ns)
            authors = [el.text for el in author_els if el.text]

            # 解析分类
            category_els = entry.findall("atom:category", ns)
            categories = [el.get("term") for el in category_els if el.get("term")]

            # arXiv ID
            arxiv_id = entry.get("xml:base", "").split("/")[-1]
            if not arxiv_id:
                id_el = entry.find("atom:id", ns)
                arxiv_id = id_el.text.split("/")[-1] if id_el is not None else ""

            # 发布日期
            published_str = get_text("published")
            try:
                published_dt = datetime.strptime(published_str[:10], "%Y-%m-%d")
            except (ValueError, IndexError):
                published_dt = datetime.utcnow()

            # 摘要（截断）
            summary = get_text("summary")
            if len(summary) > 500:
                summary = summary[:500] + "..."

            paper = {
                "external_id": arxiv_id,
                "arxiv_url": get_text("id"),
                "title": get_text("title").replace("\n", " ").strip(),
                "summary": summary,
                "authors": authors,
                "author_count": len(authors),
                "published": published_str[:10],
                "published_datetime": published_dt.isoformat(),
                "updated": get_text("updated")[:10] or None,
                "categories": categories,
                "comment": get_text("comment"),
                "doi": get_text("doi"),
                "fetched_at": datetime.utcnow().isoformat(),
            }
            papers.append(paper)

        return papers

    def fetch_by_keywords(self, keywords: List[str], days: int = 7, max_results: int = 100) -> CollectorResult:
        """
        按关键词搜索（用于关键词激增检测）

        Args:
            keywords: 关键词列表，如 ["transformer", "attention"]
            days: 时间窗口（天）
            max_results: 最大结果数
        """
        # 构建查询
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        keyword_parts = " OR ".join(f'all:"{kw}"' for kw in keywords)
        query = f"({keyword_parts}) AND submittedDate:[{date_from} TO 99991231]"

        return self._fetch_with_query(query, max_results)
