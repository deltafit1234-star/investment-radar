"""
IT桔子 融资事件采集器（Prototype - 爬虫方案）
https://www.itjuzi.com/investments

signal_type: itjuzi_funding
注意：IT桔子有反爬，403/429 时跳过（原型阶段不阻塞主流程）
"""

import time
import random
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional, List
from loguru import logger


# 常用浏览器 UA 列表（防反爬）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


class ItjuziFundingCollector:
    """IT桔子 融资事件采集（爬虫原型）"""

    signal_type = "itjuzi_funding"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.timeout = 15
        self.session = requests.Session()

    def _get_headers(self) -> dict:
        """生成随机 UA 请求头"""
        ua = random.choice(USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Referer": "https://www.itjuzi.com/",
        }
        # Cookie 来自 config（ITJUZI_COOKIE 环境变量）
        cookie = self.config.get("cookie", "")
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _fetch_page(self, url: str) -> Optional[str]:
        """获取页面 HTML"""
        try:
            resp = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            if resp.status_code in (403, 429):
                logger.warning(f"  IT桔子反爬拦截: HTTP {resp.status_code}，跳过")
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"  IT桔子请求失败: {e}")
            return None

    def _parse_funding_item(self, item) -> Optional[dict]:
        """解析单条融资记录"""
        try:
            # 公司名
            company_elem = item.select_one(".company-name") or item.select_one(
                ".name"
            ) or item.select_one("a.link-hover")
            company_name = company_elem.get_text(strip=True) if company_elem else ""

            # 融资轮次
            round_elem = item.select_one(".round") or item.select_one(
                ".funding-round"
            )
            round_type = round_elem.get_text(strip=True) if round_elem else ""

            # 金额
            amount_elem = item.select_one(".money") or item.select_one(".amount")
            amount = amount_elem.get_text(strip=True) if amount_elem else ""

            # 投资方
            investor_elem = item.select_one(".investors") or item.select_one(
                ".investor"
            )
            investors = investor_elem.get_text(strip=True) if investor_elem else ""

            # 日期
            date_elem = item.select_one(".date") or item.select_one(".time")
            date_str = date_elem.get_text(strip=True) if date_elem else ""

            # 标签（行业）
            tag_elems = item.select(".tag") or item.select(".tags span")
            tags = [t.get_text(strip=True) for t in tag_elems[:3]]

            if not company_name:
                return None

            return {
                "company_name": company_name,
                "round": round_type or "未知轮次",
                "amount": amount,
                "investors": investors,
                "date": date_str,
                "tags": tags,
                "signal_type": self.signal_type,
            }
        except Exception:
            return None

    def _parse_page(self, html: str) -> List[dict]:
        """解析整页融资记录"""
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")

            # IT桔子融资列表选择器（多组备选）
            selectors = [
                ".investment-list .investment-item",
                ".list-main .item",
                ".company-list .row",
                "ul.list-info li",
                ".main-tuwen",
            ]
            items = []
            for sel in selectors:
                items = soup.select(sel)
                if items:
                    break

            if not items:
                # 备选：直接查找所有可能包含融资信息的块
                items = soup.select("[class*='list'] [class*='item']")

            for item in items[:20]:
                record = self._parse_funding_item(item)
                if record:
                    results.append(record)

        except Exception as e:
            logger.warning(f"  IT桔子页面解析失败: {e}")

        return results

    def collect(self, keyword: str, page: int = 1) -> dict:
        """
        按关键词采集融资事件

        Args:
            keyword: 搜索关键词（赛道关键词）
            page: 页码（默认第1页）

        Returns:
            CollectionResult 格式 dict
        """
        # 请求间隔防反爬
        time.sleep(2 + random.uniform(0.5, 1.5))

        # IT桔子搜索 URL（不需要登录）
        # 实际使用其公开搜索页面
        url = f"https://www.itjuzi.com/investments?keyword={keyword}&page={page}"

        html = self._fetch_page(url)
        if not html:
            return {
                "success": False,
                "data": [],
                "total_count": 0,
                "error": "blocked_or_failed",
            }

        results = self._parse_page(html)

        # 关键词二次过滤（页面搜索不完全精准）
        if keyword:
            filtered = [
                r
                for r in results
                if keyword.lower()
                in (r["company_name"] + " ".join(r.get("tags", []))).lower()
            ]
            results = filtered if filtered else results

        return {
            "success": True,
            "data": results,
            "total_count": len(results),
            "error": None,
        }

    def run(self, keywords: List[str] = None) -> dict:
        """批量关键词搜索"""
        if keywords is None:
            keywords = []
        all_results = []
        for kw in keywords:
            result = self.collect(kw)
            if result["success"]:
                all_results.extend(result["data"])
            # 关键词间也加间隔
            time.sleep(1 + random.uniform(0, 1))

        return {
            "success": True,
            "data": all_results,
            "total_count": len(all_results),
            "error": None,
        }


def create_collector(config: dict = None) -> ItjuziFundingCollector:
    return ItjuziFundingCollector(config)
