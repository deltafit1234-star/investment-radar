"""
深度分析模块（Phase 4 — Premium 高级服务）
为 Premium 租户订阅的信号生成深度分析内容

分析内容：
- 投资机会解读
- 竞争格局分析
- 风险提示
- 相关公司/项目
- 技术成熟度评估
"""

import os
import json
import requests
from typing import Dict, Any, Optional, List
from loguru import logger


class DeepAnalyzer:
    """
    深度信号分析器 — 为 Premium 租户生成深度分析

    使用方式：
        analyzer = DeepAnalyzer()
        result = analyzer.analyze(signal_dict, track_config)
        # result["analysis_premium"] = "深度分析文本..."
    """

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        self.config = llm_config or {}
        self.model = self.config.get("model", "MiniMax-M2.7")
        self.max_tokens = self.config.get("max_tokens", 800)
        self.temperature = self.config.get("temperature", 0.5)
        self.base_url = self.config.get("base_url", "https://api.minimax.io/anthropic/v1")

        api_key = os.getenv("MINIMAX_API_KEY", "")
        self._api_key = api_key
        self._available = bool(api_key)

        if self._available:
            logger.info(f"[DeepAnalyzer] 就绪: {self.model}")
        else:
            logger.warning("[DeepAnalyzer] MINIMAX_API_KEY 未设置，跳过深度分析")

    def analyze(self, signal: Dict[str, Any], track_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        对信号进行深度分析，返回添加了 analysis_premium 的信号副本。
        仅 Star 激增和论文爆发走深度分析，其他类型返回原始信号。
        """
        result = signal.copy()
        signal_type = signal.get("type", "unknown")

        # 只对高价值信号做深度分析
        if signal_type not in ("star_surge", "paper_burst"):
            result["analysis_premium"] = None
            return result

        if not self._available:
            result["analysis_premium"] = self._mock_analysis(signal, track_config)
            return result

        try:
            prompt = self._build_prompt(signal, track_config)
            response = self._call_api(prompt)
            result["analysis_premium"] = response.strip()
            logger.info(f"[DeepAnalyzer] 分析完成: {signal.get('title', signal.get('full_name', ''))[:40]}")
        except Exception as e:
            logger.error(f"[DeepAnalyzer] 失败: {e}，降级为 mock")
            result["analysis_premium"] = self._mock_analysis(signal, track_config)

        return result

    def _build_prompt(self, signal: Dict[str, Any], track_config: Dict[str, Any]) -> str:
        signal_type = signal.get("type", "unknown")
        track_name = track_config.get("track_name", track_config.get("track_id", ""))
        title = signal.get("title") or signal.get("full_name", "")
        content = signal.get("content", "") or signal.get("summary", "")
        stars = signal.get("stars", signal.get("star_count", ""))
        change = signal.get("change", signal.get("star_change", ""))
        priority = signal.get("priority", "medium")

        if signal_type == "star_surge":
            return f"""你是一位资深科技投资分析师。请对以下开源项目进行深度投资分析。

项目：{title}
赛道：{track_name}
Stars：{stars}（变化：{change}）
现有信息：{content[:500]}

请从以下维度进行分析（简洁扼要，每点1-3句话）：

1. 投资机会：该项目的技术护城河和商业化潜力
2. 竞争格局：相比同类项目的核心差异
3. 风险提示：主要风险因素
4. 相关公司：已采用或关注该项目的知名公司（如有）
5. 技术成熟度：从 TRL（技术成熟度等级）角度评估
6. 投资建议：简短总结

请用中文回答，总字数控制在500字以内。"""

        elif signal_type == "paper_burst":
            return f"""你是一位资深科技投资分析师。请对以下学术论文爆发事件进行深度解读。

赛道：{track_name}
事件：{title}
现有信息：{content[:500]}
优先级：{priority}

请从以下维度进行分析（简洁扼要）：

1. 技术突破：该论文或论文集群代表的核心技术进展
2. 投资影响：对相关赛道的短期和中长期影响
3. 竞争格局：该方向上的主要研究力量（机构/企业）
4. 商业化路径：从论文到产品/商业应用的典型路径
5. 风险提示：技术落地的主要障碍
6. 投资建议：简短总结

请用中文回答，总字数控制在500字以内。"""

        else:
            return f"""请分析以下信号：{title}"""

    def _call_api(self, prompt: str) -> str:
        """发送请求到 MiniMax API"""
        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"API 返回 {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        content_blocks = data.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                return block["text"]
        return str(data)

    def _mock_analysis(self, signal: Dict[str, Any], track_config: Dict[str, Any]) -> str:
        """无 API Key 时的 Mock 深度分析"""
        signal_type = signal.get("type", "unknown")
        title = signal.get("title") or signal.get("full_name", "未知项目")
        track_name = track_config.get("track_name", track_config.get("track_id", ""))

        if signal_type == "star_surge":
            return f"""【深度分析 · Premium】

📌 项目：{title}
🏷️ 赛道：{track_name}

1. 投资机会：Star 激增表明市场关注度显著提升，需结合项目背景判断是技术突破还是营销驱动。

2. 竞争格局：建议与同类项目对比技术路线和社区活跃度。

3. 风险提示：开源项目依赖社区维护，需关注核心贡献者留存情况。

4. 相关公司：可搜索项目 README 或官网获取商业合作信息。

5. 技术成熟度：建议查阅项目路线图（Roadmap）和最新发布版本（Release Notes）。

⚠️ 当前为预览模式（MINIMAX_API_KEY 未配置），完整分析需配置 API Key。"""

        else:
            return f"""【深度分析 · Premium】

📌 事件：{title}
🏷️ 赛道：{track_name}

1. 技术突破：论文爆发通常代表领域热度提升，需进一步阅读论文判断是否是突破性进展。

2. 投资影响：建议关注论文通讯作者所在机构和企业合作情况。

3. 竞争格局：学术界竞争激烈，工业界落地需要关注技术转化能力。

4. 商业化路径：从论文到产品通常需要1-3年，需关注技术成熟度。

⚠️ 当前为预览模式，完整分析需配置 API Key。"""
