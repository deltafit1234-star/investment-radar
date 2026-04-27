"""
每周报告生成器
汇总本周信号，生成结构化周报
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

from .enricher import SignalEnricher


class WeeklyReportGenerator:
    """周报生成器"""

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        self.llm_config = llm_config or {}
        self.enricher = SignalEnricher(llm_config=llm_config)

    def generate(self, signals: List[Dict[str, Any]], week_start: str = None) -> str:
        """
        生成周报

        Args:
            signals: 本周信号列表
            week_start: 周起始日期（YYYY-MM-DD），默认本周一

        Returns:
            格式化的周报文本
        """
        if not signals:
            return self._empty_report()

        # 计算周起始
        if week_start:
            start_date = datetime.strptime(week_start, "%Y-%m-%d")
        else:
            today = datetime.now()
            start_date = today - timedelta(days=today.weekday())

        end_date = start_date + timedelta(days=6)

        # 按类型分组
        by_type = {}
        for sig in signals:
            t = sig.get("type", "unknown")
            by_type.setdefault(t, []).append(sig)

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_signals = sorted(
            signals,
            key=lambda s: priority_order.get(s.get("priority", "low"), 3)
        )

        # ── 构建报告框架 ─────────────────────────────────
        lines = [
            f"📊 AI大模型赛道 — 投资雷达周报",
            f"{start_date.strftime('%Y年%m月%d日')} — {end_date.strftime('%m月%d日')}",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        # 概览
        lines.extend(self._build_overview(signals, by_type, start_date, end_date))

        # 重点信号
        lines.extend(self._build_top_signals(sorted_signals, by_type))

        # 趋势洞察
        lines.extend(self._build_trends(signals, by_type))

        # 数据明细
        lines.extend(self._build_detail(signals, by_type))

        # 下周关注
        lines.extend(self._build_outlook(sorted_signals))

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📅 报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("由投资雷达自动生成")

        return "\n".join(lines)

    def _clean_md(self, text: str) -> str:
        """清理 markdown 格式"""
        if not text:
            return ""
        import re
        text = re.sub(r'\*\*|__|\*|_', '', text)
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[-•]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{2,}', ' ', text)
        text = re.sub(r'\n', ' ', text)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    def _empty_report(self) -> str:
        today = datetime.now()
        start = today - timedelta(days=today.weekday())
        return (
            f"📊 AI大模型赛道 — 投资雷达周报\n"
            f"{start.strftime('%Y年%m月%d日')} — {today.strftime('%m月%d日')}\n\n"
            f"本周暂无异常信号，继续观察。\n\n"
            f"📅 报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    def _build_overview(
        self,
        signals: List[Dict[str, Any]],
        by_type: Dict[str, list],
        start: datetime,
        end: datetime
    ) -> List[str]:
        """构建概览部分"""
        total = len(signals)
        high_priority = sum(1 for s in signals if s.get("priority") == "high")
        star_count = len(by_type.get("star_surge", []))
        paper_count = len(by_type.get("paper_burst", []))
        news_count = len(by_type.get("funding_news", [])) + len(by_type.get("model_news", []))

        lines = [
            "【本周概览】",
            f"共捕获 {total} 个信号，其中高优先级 {high_priority} 个",
            "",
        ]

        if star_count:
            lines.append(f"• GitHub Star 激增: {star_count} 个项目")
        if paper_count:
            lines.append(f"• 论文爆发: {paper_count} 个领域")
        if news_count:
            lines.append(f"• 融资/模型动态: {news_count} 条")
        if by_type.get("funding_news"):
            lines.append(f"  - 融资事件: {len(by_type['funding_news'])} 条")
        if by_type.get("model_news"):
            lines.append(f"  - 模型发布: {len(by_type['model_news'])} 条")

        lines.append("")
        return lines

    def _build_top_signals(
        self,
        sorted_signals: List[Dict[str, Any]],
        by_type: Dict[str, list]
    ) -> List[str]:
        """构建重点信号部分"""
        lines = ["【重点信号】", ""]

        # 高优先级信号
        high_priority = [s for s in sorted_signals if s.get("priority") == "high"]
        if high_priority:
            lines.append("🔥 高优先级:")
            for sig in high_priority[:5]:
                title = sig.get("title") or sig.get("full_name") or sig.get("name", "")
                summary = self._clean_md(sig.get("summary") or sig.get("content", ""))
                meaning = self._clean_md(sig.get("meaning", ""))
                signal_type = sig.get("type", "") or sig.get("signal_type", "")

                lines.append(f"  ◆ [{signal_type}] {title}")
                if summary:
                    lines.append(f"    {summary[:120]}")
                if meaning:
                    lines.append(f"    {meaning[:120]}")
                lines.append("")
        else:
            lines.append("  本周无高优先级信号")
            lines.append("")

        # Star 激增项目
        star_signals = by_type.get("star_surge", [])
        if star_signals:
            lines.append("📈 GitHub 热门项目:")
            for sig in star_signals[:5]:
                name = sig.get("full_name") or sig.get("title") or "unknown"
                stars = sig.get("stars", 0)
                growth = sig.get("growth_rate", 0)
                summary = self._clean_md(sig.get("summary") or sig.get("content", ""))
                lines.append(f"  • {name} (⭐{stars}, +{growth*100:.0f}%)")
                if summary:
                    lines.append(f"    {summary[:150]}")
            lines.append("")

        return lines

    def _build_trends(
        self,
        signals: List[Dict[str, Any]],
        by_type: Dict[str, list]
    ) -> List[str]:
        """构建趋势洞察部分"""
        lines = ["【趋势洞察】", ""]

        # 分析关联信号
        has_star = bool(by_type.get("star_surge"))
        has_paper = bool(by_type.get("paper_burst"))
        has_funding = bool(by_type.get("funding_news"))
        has_model = bool(by_type.get("model_news"))

        if has_star and has_paper:
            lines.append("  🔗 GitHub热度与论文研究呈现同步升温，")
            lines.append("     反映大模型底层优化成为当前技术热点。")
            lines.append("")

        if has_funding:
            lines.append("  💰 融资市场活跃，资本持续布局AI赛道，")
            lines.append("     建议关注头部项目的商业化进展。")
            lines.append("")

        if has_model:
            lines.append("  🤖 新模型发布频繁，技术迭代速度加快，")
            lines.append("     基础模型和应用层的创新都在加速。")
            lines.append("")

        # 分析 Star 增长最快的方向
        star_signals = by_type.get("star_surge", [])
        if star_signals:
            # 提取共同主题（从 description 中找关键词）
            all_text = " ".join([
                (s.get("description") or "") + " " + (s.get("summary") or "") + " " + (s.get("content") or "")
                for s in star_signals
            ])
            themes = self._extract_themes(all_text)
            if themes:
                lines.append(f"  📌 本周技术主题: {', '.join(themes[:3])}")
                lines.append("")

        if len(lines) == 2:  # 只有标题
            lines.append("  本周趋势不明显，建议持续观察。")
            lines.append("")

        return lines

    def _build_detail(
        self,
        signals: List[Dict[str, Any]],
        by_type: Dict[str, list]
    ) -> List[str]:
        """构建数据明细部分"""
        lines = ["【数据明细】", ""]

        # Star 增长明细
        star_signals = by_type.get("star_surge", [])
        if star_signals:
            lines.append("GitHub Star 增长:")
            for sig in star_signals:
                name = sig.get("full_name") or sig.get("title") or "unknown"
                stars = sig.get("stars", 0)
                growth = sig.get("growth_rate", 0)
                url = sig.get("url", "")
                summary = self._clean_md(sig.get("summary") or sig.get("content", ""))
                lines.append(f"  • {name} ⭐{stars} | +{growth*100:.0f}%")
                if summary:
                    lines.append(f"    {summary[:100]}")
                if url:
                    lines.append(f"    {url}")
            lines.append("")

        # 论文爆发明细
        paper_signals = by_type.get("paper_burst", [])
        if paper_signals:
            lines.append("论文爆发领域:")
            for sig in paper_signals:
                # 从 message 或 content 获取领域信息
                msg = sig.get("message", "")
                domain = sig.get("domain", "AI/ML")
                count = sig.get("count", 0)
                lines.append(f"  • {domain}: {count} 篇新论文")
                if msg:
                    lines.append(f"    {msg[:80]}")
            lines.append("")

        # 新闻明细
        news_signals = by_type.get("funding_news", []) + by_type.get("model_news", [])
        if news_signals:
            lines.append("重要新闻:")
            for sig in news_signals[:10]:
                title = sig.get("title") or sig.get("full_name") or ""
                url = sig.get("url", "")
                signal_type = sig.get("type", "") or sig.get("signal_type", "")
                lines.append(f"  • [{signal_type}] {title}")
                if url:
                    lines.append(f"    {url[:80]}")
            lines.append("")

        return lines

    def _build_outlook(self, sorted_signals: List[Dict[str, Any]]) -> List[str]:
        """构建下周关注部分"""
        lines = ["【下周关注】", ""]

        # 基于高优先级信号推荐关注
        high_priority = [s for s in sorted_signals if s.get("priority") == "high"]
        star_signals = [s for s in sorted_signals if s.get("type") == "star_surge"]

        if star_signals:
            lines.append("  建议持续跟踪以下项目:")
            for sig in star_signals[:3]:
                name = sig.get("full_name") or sig.get("title") or "unknown"
                url = sig.get("url", "")
                lines.append(f"  • {name}")
                if url:
                    lines.append(f"    {url}")
            lines.append("")

        if high_priority:
            lines.append("  高优先级事项:")
            for sig in high_priority[:3]:
                title = sig.get("title") or sig.get("full_name") or ""
                meaning = self._clean_md(sig.get("meaning", ""))
                lines.append(f"  • {title}")
                if meaning:
                    lines.append(f"    {meaning[:120]}")
            lines.append("")

        if len(lines) == 2:
            lines.append(" 暂无重点关注事项。")
            lines.append("")

        return lines

    def _extract_themes(self, text: str, top_n: int = 3) -> List[str]:
        """从文本中提取主要技术主题"""
        # 简单关键词匹配
        theme_keywords = {
            "LLM/大语言模型": ["llm", "language model", "大模型", "gpt", "chatgpt"],
            "GPU/算力优化": ["gpu", "cuda", "kernel", "tiling", "算子", "推理优化"],
            "多模态": ["multimodal", "多模态", "vision", "图像", "视频"],
            "Agent/智能体": ["agent", "智能体", "autonomous", "tool"],
            "开源模型": ["open source", "开源", "llama", "mistral"],
            "AI编程": ["coding", "copilot", "cursor", "code", "编程"],
            "AI安全": ["safety", "alignment", "rlhf", "安全", "对齐"],
        }

        text_lower = text.lower()
        scores = {}
        for theme, keywords in theme_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[theme] = score

        sorted_themes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [t for t, _ in sorted_themes[:top_n]]
