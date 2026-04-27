"""
36kr 文章正文抓取器
根据 RSS feed 中的 URL 抓取完整文章内容
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger

from .base import BaseCollector, CollectorResult


class News36krArticleCollector(BaseCollector):
    """
    36kr 文章正文采集器

    从 RSS 条目获取 URL，再抓取全文内容
    用于补充 RSS 摘要的正文部分
    """

    ARTICLE_URL_TEMPLATE = "https://36kr.com/p/{article_id}"

    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.fetch_limit = self.params.get("fetch_limit", 10)  # 最多抓取篇数
        self.content_min_chars = self.params.get("content_min_chars", 200)  # 正文最低字数

    def fetch(self) -> CollectorResult:
        """
        抓取 36kr 文章正文

        注意：这个采集器需要依赖 RSS feed 的 URL 列表
        通常由调用方传入 urls 参数
        """
        urls = self.params.get("urls", [])
        if not urls:
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error="未提供文章 URL 列表"
            )

        articles = []
        errors = []

        for url in urls[:self.fetch_limit]:
            try:
                article = self._fetch_article(url)
                if article:
                    articles.append(article)
            except Exception as e:
                errors.append(f"{url}: {e}")
                logger.warning(f"抓取文章失败 {url}: {e}")

        success = len(articles) > 0
        logger.info(f"36kr 文章抓取完成: {len(articles)} 成功 / {len(errors)} 失败")

        return CollectorResult(
            source_id=self.source_id,
            success=success,
            data=articles,
            error="; ".join(errors) if errors else None
        )

    def _fetch_article(self, url: str) -> Optional[Dict[str, Any]]:
        """抓取单篇文章正文"""
        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            response.encoding = "utf-8"

            soup = BeautifulSoup(response.text, "html.parser")

            # 提取文章ID
            article_id = self._extract_article_id(url)

            # 提取标题
            title = self._extract_title(soup)

            # 提取作者
            author = self._extract_author(soup)

            # 提取发布时间
            publish_time = self._extract_publish_time(soup)

            # 提取正文
            content = self._extract_content(soup)

            if not content or len(content) < self.content_min_chars:
                logger.debug(f"文章正文过短或为空: {url}")
                return None

            # 提取标签
            tags = self._extract_tags(soup)

            return {
                "article_id": article_id,
                "url": url,
                "title": title,
                "author": author,
                "published_at": publish_time,
                "content": content,
                "content_length": len(content),
                "tags": tags,
                "source": "36kr",
                "fetched_at": datetime.utcnow().isoformat(),
            }

        except requests.exceptions.RequestException as e:
            logger.warning(f"请求失败: {url} - {e}")
            return None
        except Exception as e:
            logger.warning(f"解析失败: {url} - {e}")
            return None

    def _extract_article_id(self, url: str) -> str:
        """从 URL 提取文章 ID"""
        import re
        match = re.search(r'/p/(\d+)', url)
        return match.group(1) if match else url

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取文章标题"""
        # 优先找 meta title
        title = soup.find("meta", attrs={"name": "title"})
        if title and title.get("content"):
            return title["content"].strip()

        # 其次找 og:title
        title = soup.find("meta", property="og:title")
        if title and title.get("content"):
            return title["content"].strip()

        # 再次找 h1
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        # 最后用 title tag
        title_tag = soup.find("title")
        if title_tag:
            text = title_tag.get_text(strip=True)
            # 去掉网站后缀
            return text.split("|")[0].split("_")[0].strip()

        return ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """提取作者"""
        # 找 meta author
        author = soup.find("meta", attrs={"name": "author"})
        if author and author.get("content"):
            return author["content"].strip()

        # 找 itemprop author
        author = soup.find("span", itemprop="author")
        if author:
            return author.get_text(strip=True)

        # 找 class 包含 author 的元素
        for el in soup.find_all(class_=True):
            cls = " ".join(el.get("class", []))
            if "author" in cls.lower() and "name" in cls.lower():
                return el.get_text(strip=True)

        return ""

    def _extract_publish_time(self, soup: BeautifulSoup) -> str:
        """提取发布时间"""
        # 找 meta article:published_time
        time_el = soup.find("meta", property="article:published_time")
        if time_el and time_el.get("content"):
            return time_el["content"].strip()

        # 找 time 标签
        time_el = soup.find("time")
        if time_el:
            return time_el.get("datetime") or time_el.get_text(strip=True)

        # 找 class 包含 time 的 span
        for el in soup.find_all(class_=True):
            cls = " ".join(el.get("class", []))
            if "time" in cls.lower() or "date" in cls.lower():
                text = el.get_text(strip=True)
                if any(c.isdigit() for c in text):
                    return text

        return ""

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取文章正文"""
        # 优先找 article-content
        content_el = soup.select_one("div.article-content")
        if content_el:
            return self._clean_text(content_el)

        # 备选：找 itemprop=articleBody
        content_el = soup.find("div", itemprop="articleBody")
        if content_el:
            return self._clean_text(content_el)

        # 备选：找 class 包含 content 的最大 div
        best_el = None
        best_len = 0
        for el in soup.find_all("div", class_=True):
            cls = " ".join(el.get("class", []))
            if "content" in cls.lower() and "article" in cls.lower():
                text = el.get_text(strip=True)
                if len(text) > best_len:
                    best_len = len(text)
                    best_el = el

        if best_el:
            return self._clean_text(best_el)

        return ""

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """提取文章标签"""
        tags = []

        # 找 meta keywords
        meta_kw = soup.find("meta", attrs={"name": "keywords"})
        if meta_kw and meta_kw.get("content"):
            tags = [t.strip() for t in meta_kw["content"].split(",")]

        # 找 class 包含 tag 的 a 标签
        for a in soup.find_all("a", class_=True):
            cls = " ".join(a.get("class", []))
            if "tag" in cls.lower():
                text = a.get_text(strip=True)
                if text and text not in tags:
                    tags.append(text)

        return tags[:10]  # 最多10个标签

    def _clean_text(self, element) -> str:
        """清理 HTML 元素中的文本"""
        # 移除脚本和样式
        for tag in element.find_all(["script", "style", "noscript"]):
            tag.decompose()

        text = element.get_text(separator="\n", strip=True)

        # 移除多余空行
        import re
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()
