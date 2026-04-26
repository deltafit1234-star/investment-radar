"""
HuggingFace Models 采集器
采集 HuggingFace 热门模型列表
"""

import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger

from .base import BaseCollector, CollectorResult


class HuggingFaceCollector(BaseCollector):
    """HuggingFace 模型采集器"""

    BASE_URL = "https://huggingface.co/api"

    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "InvestmentRadar/1.0",
            "Accept": "application/json",
        })

    def fetch(self) -> CollectorResult:
        """
        采集 HuggingFace 热门模型

        支持的排序方式:
        - trending: trending models
        - downloads: most downloaded
        - likes: most liked
        """
        sort = self.params.get("sort", "trending")
        limit = min(self.params.get("limit", 50), 100)

        url = f"{self.BASE_URL}/models"
        params = {"sort": sort, "limit": limit}

        # 可选过滤器
        if self.params.get("filter"):
            params["filter"] = self.params["filter"]
        if self.params.get("search"):
            params["search"] = self.params["search"]

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            normalized_data = []
            for model in data:
                normalized = self._normalize_model(model)
                if normalized:
                    normalized_data.append(normalized)

            logger.debug(f"HuggingFace: 获取到 {len(normalized_data)} 个模型")

            return CollectorResult(
                source_id=self.source_id,
                success=True,
                data=normalized_data
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"HuggingFace API 请求失败: {e}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"API请求失败: {str(e)}"
            )
        except Exception as e:
            logger.error(f"HuggingFace 数据处理异常: {e}")
            return CollectorResult(
                source_id=self.source_id,
                success=False,
                error=f"数据处理异常: {str(e)}"
            )

    def _normalize_model(self, model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将 HuggingFace 模型数据标准化"""
        try:
            model_id = model.get("id") or model.get("modelId", "")
            if not model_id:
                return None

            # 下载量/热度
            downloads = model.get("downloads", 0)
            likes = model.get("likes", 0)
            # trending score（如果存在）
            trending = model.get("trending", False)

            # 标签
            tags = model.get("tags", [])
            if isinstance(tags, dict):
                tags = list(tags.keys())

            # 管道类型（如 text-generation, image-classification 等）
            pipeline_tag = model.get("pipeline_tag", "")

            # 模型卡地址
            url = f"https://huggingface.co/{model_id}"

            # 作者
            author = model_id.split("/")[0] if "/" in model_id else ""

            # 描述
            description = model.get("description", "") or ""

            return {
                "model_id": model_id,
                "author": author,
                "url": url,
                "description": description[:300],
                "downloads": downloads,
                "likes": likes,
                "trending": trending,
                "pipeline_tag": pipeline_tag,
                "tags": tags[:20],
                "created_at": model.get("createdAt", ""),
                "last_modified": model.get("lastModified", ""),
                "source": "huggingface",
                "fetched_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.warning(f"解析模型数据失败: {e}")
            return None
