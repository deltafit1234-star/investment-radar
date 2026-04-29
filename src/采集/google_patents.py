"""
Google Patents 专利趋势采集器（Prototype）
使用 Google Patents 公开搜索 API（免费，无需认证）

signal_type: patent_trend
"""

import requests
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup
from loguru import logger


class GooglePatentsCollector:
    """Google Patents 专利趋势采集"""

    signal_type = "patent_trend"
    base_url = "https://patents.google.com/query"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.timeout = 15

    def collect(self, keyword: str, max_results: int = 10) -> dict:
        """
        按关键词搜索专利

        Args:
            keyword: 搜索关键词（通常是赛道关键词）
            max_results: 最大结果数

        Returns:
            CollectionResult 格式 dict
        """
        try:
            params = {
                "q": keyword,
                "count": min(max_results, 20),
                "sort": "date",
            }
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            }

            resp = requests.get(
                self.base_url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            patents = self._parse_html(resp.text, keyword)

            return {
                "success": True,
                "data": patents,
                "total_count": len(patents),
                "error": None,
            }

        except requests.exceptions.Timeout:
            logger.warning(f"  Google Patents 超时: {keyword}")
            return {"success": False, "data": [], "total_count": 0, "error": "timeout"}
        except requests.exceptions.RequestException as e:
            logger.warning(f"  Google Patents 请求失败: {e}")
            return {"success": False, "data": [], "total_count": 0, "error": str(e)}
        except Exception as e:
            logger.exception(f"  Google Patents 异常: {e}")
            return {"success": False, "data": [], "total_count": 0, "error": str(e)}

    def _parse_html(self, html: str, keyword: str) -> list:
        """解析 Google Patents 搜索结果页面"""
        patents = []
        try:
            soup = BeautifulSoup(html, "html.parser")

            # 搜索结果项：<article> 或带 data-dna-id 的元素
            items = soup.select("article.search-result") or soup.select(
                ".patent-result"
            ) or soup.select("[data-dna-id]")

            if not items:
                # 备选：解析 JSON 数据块
                return self._parse_json_block(html, keyword)

            for item in items[:10]:
                try:
                    # 专利号
                    number_elem = (
                        item.select_one(".patent-number")
                        or item.select_one("[itemprop='publicationNumber']")
                        or item.select_one("h3")
                    )
                    patent_number = number_elem.get_text(strip=True) if number_elem else ""

                    # 标题
                    title_elem = (
                        item.select_one(".title")
                        or item.select_one("[itemprop='name']")
                        or item.select_one("h3 a")
                    )
                    title = title_elem.get_text(strip=True) if title_elem else ""

                    # 申请人
                    applicant_elem = item.select_one(
                        "[itemprop='assigneeOriginal']"
                    ) or item.select_one(".assignee")
                    applicant = (
                        applicant_elem.get_text(strip=True)
                        if applicant_elem
                        else ""
                    )

                    # 日期
                    date_elem = item.select_one(
                        "[itemprop='publicationDate']"
                    ) or item.select_one(".date")
                    date_str = date_elem.get_text(strip=True) if date_elem else ""

                    # 摘要
                    abstract_elem = item.select_one(
                        "[itemprop='abstract']"
                    ) or item.select_one(".abstract")
                    abstract = (
                        abstract_elem.get_text(strip=True)[:300]
                        if abstract_elem
                        else ""
                    )

                    if not title:
                        continue

                    patents.append({
                        "id": patent_number,
                        "title": title,
                        "patent_number": patent_number,
                        "applicant": applicant,
                        "date": date_str,
                        "abstract": abstract,
                        "keyword": keyword,
                        "url": f"https://patents.google.com/patent/{patent_number.replace(' ', '').replace('/', '')}",
                        "signal_type": self.signal_type,
                    })
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"  HTML 解析失败: {e}")

        return patents

    def _parse_json_block(self, html: str, keyword: str) -> list:
        """备选：从页面 JSON 数据块解析"""
        patents = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            scripts = soup.find_all("script", {"type": "application/ld+json"})
            for script in scripts:
                try:
                    import json

                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data[:10]:
                            if item.get("@type") == "Patent":
                                patents.append({
                                    "id": item.get("publicationNumber", ""),
                                    "title": item.get("name", ""),
                                    "patent_number": item.get("publicationNumber", ""),
                                    "applicant": (
                                        item.get(" applicant", {}).get("name", "")
                                        if isinstance(item.get(" applicant"), dict)
                                        else ""
                                    ),
                                    "date": item.get("publicationDate", ""),
                                    "abstract": item.get("description", "")[:300],
                                    "keyword": keyword,
                                    "url": item.get("url", ""),
                                    "signal_type": self.signal_type,
                                })
                except Exception:
                    continue
        except Exception:
            pass
        return patents

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


def create_collector(config: dict = None) -> GooglePatentsCollector:
    return GooglePatentsCollector(config)
