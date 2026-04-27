"""
arXiv PDF 全文抓取
下载 PDF → 提取正文 → 返回文本
"""

import re
import io
import os
import requests
from loguru import logger
from typing import Optional
from pathlib import Path

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    logger.warning("PyMuPDF 未安装，PDF 解析将使用备用方案")


class ArxivPDFDownloader:
    """arXiv PDF 下载与全文提取"""

    PDF_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "arxiv_pdf"

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or self.PDF_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def download_pdf(self, paper_id: str, arxiv_url: str = None) -> Optional[bytes]:
        """
        下载 arXiv PDF
        paper_id: 如 "2404.12345"（不带版本号）或 "2404.12345v1"
        """
        # 构建 PDF URL
        if arxiv_url and "arxiv.org" in arxiv_url:
            pdf_url = arxiv_url.replace("/abs/", "/pdf/") + ".pdf"
        else:
            paper_clean = paper_id.split("v")[0]  # 去掉版本号
            pdf_url = f"https://arxiv.org/pdf/{paper_clean}.pdf"

        cache_path = self.cache_dir / f"{paper_id}.pdf"

        # 缓存命中
        if cache_path.exists():
            logger.debug(f"  PDF 缓存命中: {paper_id}")
            return cache_path.read_bytes()

        logger.info(f"  下载 PDF: {pdf_url}")
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; InvestmentRadar/1.0)",
            }
            r = requests.get(pdf_url, headers=headers, timeout=30, stream=True)
            if r.status_code != 200:
                logger.warning(f"  PDF 下载失败 [{r.status_code}]: {paper_id}")
                return None

            content = r.content

            # 检查是否是 PDF（不以 %PDF 开头说明被重定向了）
            if not content[:4] == b"%PDF":
                logger.warning(f"  返回内容不是 PDF: {paper_id}")
                return None

            # 写入缓存
            cache_path.write_bytes(content)
            logger.info(f"  PDF 已缓存: {cache_path.stat().st_size / 1024:.0f} KB")
            return content

        except requests.exceptions.Timeout:
            logger.warning(f"  PDF 下载超时: {paper_id}")
            return None
        except Exception as e:
            logger.warning(f"  PDF 下载异常: {paper_id} — {e}")
            return None

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """从 PDF bytes 提取纯文本"""
        if not HAS_PYMUPDF:
            return self._extract_text_fallback(pdf_bytes)

        import tempfile

        try:
            # 写入临时文件（避免 stream 导致的内存问题）
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            try:
                doc = fitz.open(tmp_path)
                text_parts = []

                for page_num in range(min(len(doc), 50)):  # 最多50页
                    page = doc[page_num]
                    text = page.get_text("text")
                    if text.strip():
                        text_parts.append(f"[Page {page_num + 1}]\n{text}")

                page_count = len(doc)
                doc.close()

                full_text = "\n\n".join(text_parts)
                logger.debug(f"  提取文本: {len(full_text)} 字符, {page_count} 页")
                return full_text

            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.warning(f"  PyMuPDF 解析失败: {e}")
            return self._extract_text_fallback(pdf_bytes)

    def _extract_text_fallback(self, pdf_bytes: bytes) -> str:
        """备用文本提取（直接搜索 PDF 中的文本流）"""
        try:
            content = pdf_bytes.decode("latin-1", errors="replace")

            # 简单提取：找括号字符串（PDF 中的文本表示）
            texts = re.findall(r"\(([^)\\\\]*(?:\\\\.[^)\\\\]*)*)\)", content)
            clean_texts = []

            for t in texts:
                # 清理 PDF 转义序列
                t = re.sub(r"\\\\([nrt()\\])", r"\1", t)
                t = t.strip()
                if len(t) > 5 and not t.startswith("-"):
                    clean_texts.append(t)

            result = " ".join(clean_texts[:500])  # 限制长度
            return result[:5000]  # 最多5000字

        except Exception as e:
            logger.warning(f"  备用解析失败: {e}")
            return ""

    def fetch_full_text(self, paper_id: str, arxiv_url: str = None) -> Optional[str]:
        """
        一步到位：下载 PDF + 提取全文
        返回纯文本，或 None（失败时）
        """
        pdf_bytes = self.download_pdf(paper_id, arxiv_url)
        if not pdf_bytes:
            return None

        text = self.extract_text_from_pdf(pdf_bytes)
        if not text.strip():
            logger.warning(f"  PDF 文本提取为空: {paper_id}")
            return None

        logger.info(f"  全文提取完成: {paper_id} — {len(text)} 字符")
        return text
