"""LLM 信号丰富化模块
使用 LLM 为原始信号补充上下文和含义解读
"""

import os
import re
import json
import requests
from typing import Dict, Any, Optional
from loguru import logger


class SignalEnricher:
    """信号丰富化器"""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        self.config = llm_config or {}
        self.model = self.config.get("model", "MiniMax-M2.7")
        self.max_tokens = self.config.get("max_tokens", 500)
        self.temperature = self.config.get("temperature", 0.7)
        self.base_url = self.config.get("base_url", "https://api.minimax.io/anthropic/v1")
        
        api_key = os.getenv("MINIMAX_API_KEY", "")
        self._api_key = api_key
        self._available = bool(api_key)
        
        if self._available:
            logger.info(f"LLM 丰富化就绪: {self.model} @ {self.base_url}")
        else:
            logger.warning("MINIMAX_API_KEY 未设置，使用 mock 模式")
    
    def enrich(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        signal_type = signal.get("type", "unknown")
        
        if not self._available:
            return self._mock_enrich(signal, signal_type)
        
        try:
            return self._llm_enrich(signal, signal_type)
        except Exception as e:
            logger.error(f"LLM 丰富化失败: {e}，降级为 mock")
            return self._mock_enrich(signal, signal_type)
    
    def _llm_enrich(self, signal: Dict[str, Any], signal_type: str) -> Dict[str, Any]:
        """调用 MiniMax M2.7 API"""
        enriched = signal.copy()
        
        if signal_type == "star_surge":
            prompt = self._build_star_prompt(signal)
        elif signal_type == "paper_burst":
            prompt = self._build_paper_prompt(signal)
        else:
            prompt = self._build_generic_prompt(signal)
        
        response = self._call_api(prompt)
        
        # 解析响应
        try:
            resp_data = json.loads(response)
            content_blocks = resp_data.get("content", [])
            text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text = block["text"]
                    break
            
            # 尝试从文本中提取 summary 和 meaning
            summary, meaning = self._parse_response(text, signal_type)
            enriched["summary"] = summary
            enriched["meaning"] = meaning
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"响应解析失败: {e}，原始文本: {response[:200]}")
            enriched["summary"] = response[:200]
            enriched["meaning"] = "LLM 解读可用"
        
        return enriched
    
    def _call_api(self, prompt: str) -> str:
        """发送请求到 MiniMax API"""
        url = f"{self.base_url}/messages"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.text
    
    def _parse_response(self, text: str, signal_type: str) -> tuple:
        """解析 LLM 文本响应，提取 summary 和 meaning"""
        if not text:
            return "无内容", "需人工判断"
        
        summary = text.strip()[:200]
        meaning = "深度解读可用"
        
        # 匹配各种 header 格式
        # 模式1: **1. 一句话概括** 或 **概括** 等
        # 模式2: 一句话概括：xxx 或 概括：xxx
        # 模式3: 1. xxx（段落开头）
        lines = text.strip().split("\n")
        captured_meaning = None
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # 跳过空行
            if not line:
                i += 1
                continue
            
            # 检测 summary 标记
            is_summary = any(k in line for k in ["一句话概括", "概括", "概括为", "概括：", "值得原因", "值得关注原因"])
            is_meaning = any(k in line for k in ["趋势", "价值", "解读", "分析", "研究价值", "投资价值"])
            
            if is_summary and not is_meaning:
                # 取下一行作为 summary（当前行是标题）
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not any(k in next_line for k in ["**", "##", "趋势", "价值", "解读"]):
                        summary = next_line[:200]
                        i += 1
                    else:
                        # 标题后面还是标题，找下一个非空行
                        for j in range(i + 1, min(i + 4, len(lines))):
                            if lines[j].strip() and not lines[j].strip().startswith("**"):
                                summary = lines[j].strip()[:200]
                                i = j
                                break
                        i += 1
                else:
                    summary = line[:200]
                    i += 1
            elif is_meaning:
                # meaning: 取后续段落
                para_lines = []
                for j in range(i + 1, len(lines)):
                    l = lines[j].strip()
                    if l.startswith("**") or l.startswith("##") or l.startswith("---"):
                        break
                    if l:
                        para_lines.append(l)
                    if len(para_lines) >= 3:
                        break
                if para_lines:
                    captured_meaning = " ".join(para_lines)[:200]
                i += 1
            else:
                # 普通行，检查是否是 summary 内容（短句开头）
                if len(line) < 100 and not line.startswith("**") and "。" in line:
                    summary = line[:200]
                i += 1
        
        if captured_meaning:
            meaning = captured_meaning
        
        return summary[:200], meaning[:200]
    
    def _build_star_prompt(self, signal: Dict) -> str:
        name = signal.get("full_name", "")
        repo_url = signal.get("url", "")
        stars = signal.get("stars", 0)
        growth = signal.get("growth_rate", 0)
        description = signal.get("description", "")
        language = signal.get("language", "")
        
        return f"""分析以下 GitHub 项目并给出简要评估。

项目信息:
- 名称: {name}
- 地址: {repo_url}
- 描述: {description}
- 语言: {language}
- Star 数: {stars}
- 增长率: {growth*100:.0f}%

请直接回答（不用 JSON 格式）：
1. 一句话概括该项目值得关注的原因（50字内）
2. 该项目增长代表什么趋势、有什么投资/研究价值（100字内）"""

    def _build_paper_prompt(self, signal: Dict) -> str:
        count = signal.get("count", 0)
        domain = signal.get("domain", "")
        papers = signal.get("papers", [])
        
        paper_list = "\n".join([f"- {p}" for p in papers[:5]]) if papers else "（论文列表未提供）"
        
        return f"""分析以下 arXiv 论文激增信号并给出专业评估。

信号信息:
- 领域: {domain}
- 新增论文数: {count} 篇
- 论文列表:
{paper_list}

请直接回答（不用 JSON 格式）：
1. 概括该领域的研究热点（50字内）
2. 这批论文代表什么技术趋势、有什么投资/研究价值（100字内）"""
    
    def _build_generic_prompt(self, signal: Dict) -> str:
        return f"""分析以下信号并给出简要评估。

信号内容: {signal.get("content", "")}
类型: {signal.get("type", "")}

请直接回答：
1. 一句话概括（50字内）
2. 深度解读（100字内）"""
    
    def _mock_enrich(self, signal: Dict[str, Any], signal_type: str) -> Dict[str, Any]:
        """Mock 模式：用于演示或 API 不可用时"""
        enriched = signal.copy()
        
        if signal_type == "star_surge":
            enriched["summary"] = self._mock_summarize_star(signal)
            enriched["meaning"] = self._mock_interpret_star(signal)
        elif signal_type == "paper_burst":
            enriched["summary"] = self._mock_summarize_paper(signal)
            enriched["meaning"] = self._mock_interpret_paper(signal)
        else:
            enriched["summary"] = signal.get("content", "")[:200]
            enriched["meaning"] = "需人工判断"
        
        return enriched
    
    def batch_enrich(self, signals: list) -> list:
        return [self.enrich(s) for s in signals]
    
    def _mock_summarize_star(self, signal: Dict) -> str:
        name = signal.get("full_name", "")
        stars = signal.get("stars", 0)
        growth = signal.get("growth_rate", 0)
        return f"{name} 的 Star 数量达到 {stars}，较之前增长 {growth*100:.0f}%"
    
    def _mock_interpret_star(self, signal: Dict) -> str:
        name = signal.get("full_name", "")
        growth = signal.get("growth_rate", 0)
        if growth > 0.5:
            return f"🔥 {name} 增长迅猛，可能代表新的技术趋势或应用方向，建议关注"
        elif growth > 0.3:
            return f"📈 {name} 增长较快，值得关注其发展动态"
        else:
            return f"📊 {name} 有一定增长，可持续观察"
    
    def _mock_summarize_paper(self, signal: Dict) -> str:
        return f"相关领域新增论文 {signal.get('count', 0)} 篇"
    
    def _mock_interpret_paper(self, signal: Dict) -> str:
        return "论文数量激增可能代表技术突破或研究热点，建议关注"
