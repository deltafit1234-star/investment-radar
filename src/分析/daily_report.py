"""
每日投资情报报告生成器（Phase 2 - Premium专属）
每赛道独立生成一份报告，每日最多一篇
静默日（信号<3）→ 信号合并至第一个非静默日
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger


class DailyReportGenerator:
    """每日情报报告生成器"""

    # 静默日阈值
    SILENT_THRESHOLD = 3

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        self.llm_config = llm_config or {}

    def generate(
        self,
        track_id: str,
        track_name: str,
        signals: List[Dict[str, Any]],
        report_date: str = None,
        merged_signals: List[Dict[str, Any]] = None,
        is_silent: bool = False,
    ) -> dict:
        """
        生成每日报告

        Args:
            track_id: 赛道ID
            track_name: 赛道名称
            signals: 当日有效信号
            report_date: 报告日期（YYYY-MM-DD），默认今天
            merged_signals: 合并过来的历史信号（静默日合并）
            is_silent: 是否为静默日

        Returns:
            dict: {
                "track_id": str,
                "track_name": str,
                "date": str,
                "is_silent": bool,
                "signal_count": int,
                "report_text": str,   # 推送用的文本
                "report_data": dict,  # 完整报告数据（存库用）
                "themes": list,       # 主题分组
            }
        """
        if report_date is None:
            report_date = datetime.now().strftime("%Y-%m-%d")

        merged = merged_signals or []
        all_signals = signals + merged

        if is_silent or len(all_signals) < self.SILENT_THRESHOLD:
            return self._generate_silent_report(
                track_id, track_name, report_date, all_signals
            )

        # 按类型分组
        by_type = self._group_by_type(all_signals)

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_signals = sorted(
            all_signals,
            key=lambda s: priority_order.get(s.get("priority", "low"), 3),
        )

        # 主题分组
        themes = self._build_themes(all_signals)

        # 构建报告文本
        lines = self._build_report_lines(
            track_id, track_name, report_date,
            all_signals, sorted_signals, by_type, themes, merged
        )
        report_text = "\n".join(lines)

        report_data = {
            "track_id": track_id,
            "track_name": track_name,
            "date": report_date,
            "is_silent": is_silent,
            "signal_count": len(all_signals),
            "high_priority_count": sum(
                1 for s in all_signals if s.get("priority") == "high"
            ),
            "themes": themes,
            "merged_count": len(merged),
            "report_text": report_text,
            "raw_signals": all_signals,
        }

        return {
            "track_id": track_id,
            "track_name": track_name,
            "date": report_date,
            "is_silent": is_silent,
            "signal_count": len(all_signals),
            "report_text": report_text,
            "report_data": report_data,
            "themes": themes,
        }

    def _generate_silent_report(
        self,
        track_id: str,
        track_name: str,
        report_date: str,
        signals: List[Dict[str, Any]],
    ) -> dict:
        """静默日报（信号不足时生成占位报告）"""
        lines = [
            f"📊 {track_name} — 投资雷达日报",
            f"{report_date}",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "【今日概况】",
            f"今日信号 < {self.SILENT_THRESHOLD} 个（静默日）",
            "信号已合并至明日报告",
            "",
        ]

        if signals:
            lines.append("【历史信号回顾】")
            for sig in signals[:5]:
                title = sig.get("full_name") or sig.get("title", "")[:50]
                sig_type = sig.get("type") or sig.get("signal_type", "") or "unknown"
                lines.append(f"  • [{sig_type}] {title}")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"📅 报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "由投资雷达自动生成 · Premium专属",
        ])

        return {
            "track_id": track_id,
            "track_name": track_name,
            "date": report_date,
            "is_silent": True,
            "signal_count": len(signals),
            "report_text": "\n".join(lines),
            "report_data": {
                "track_id": track_id,
                "track_name": track_name,
                "date": report_date,
                "is_silent": True,
                "signal_count": len(signals),
                "report_text": "\n".join(lines),
            },
            "themes": [],
        }

    def _group_by_type(self, signals: List[Dict[str, Any]]) -> Dict[str, list]:
        """按信号类型分组"""
        by_type: Dict[str, list] = {}
        for sig in signals:
            t = sig.get("type") or sig.get("signal_type") or "unknown"
            by_type.setdefault(t, []).append(sig)
        return by_type

    def _build_themes(self, signals: List[Dict[str, Any]]) -> List[dict]:
        """从信号中提取主题分组（简单规则版，无LLM调用）"""
        themes_map: Dict[str, list] = {}

        for sig in signals:
            sig_type = sig.get("type") or sig.get("signal_type", "") or "unknown"
            title = sig.get("full_name") or sig.get("title", "")
            content = sig.get("content", "") or ""

            # 主题识别：优先按内容关键词，其次按信号类型
            # funding_news 也走内容匹配，避免融资新闻被统一归类
            if sig_type in ("star_surge", "hackernews_hot", "funding_news", "itjuzi_funding"):
                if any(k in (title+content).lower() for k in ["llm", "gpt", "language model", "大模型", "chatgpt", "openai", "claude", "gemini"]):
                    theme = "AI大模型/基础模型"
                elif any(k in (title+content).lower() for k in ["robot", "机械臂", "人形机器人", "具身智能", "擎天柱", "宇树", "智元", " Figure", "Tesla Bot"]):
                    theme = "机器人/自动化"
                elif any(k in (title+content).lower() for k in ["chip", "半导体", "gpu", "芯片", "光刻", "晶圆", "集成电路"]):
                    theme = "半导体/芯片"
                elif any(k in (title+content).lower() for k in ["brain", "脑机", "BCI", "neural", "神经接口", "neurosity"]):
                    theme = "脑机接口"
                elif any(k in (title+content).lower() for k in ["auto", "驾驶", "vehicle", "ev", "智能驾驶", "无人车", "robotaxi"]):
                    theme = "自动驾驶/新能源"
                elif any(k in (title+content).lower() for k in ["energy", "solar", "储能", "电池", "锂电", "钠电", "新能源", "碳中和"]):
                    theme = "新能源"
                elif sig_type in ("funding_news", "itjuzi_funding"):
                    theme = "融资/投资动态"
                else:
                    theme = "其他技术热点"
            elif sig_type in ("paper_burst", "patent_trend"):
                theme = "学术/专利趋势"
            elif sig_type == "techcrunch_news":
                theme = "国际科技动态"
            else:
                theme = "综合动态"

            themes_map.setdefault(theme, []).append(sig)

        # 转换为列表
        themes = []
        priority_order = {"high": 0, "medium": 1, "low": 2}
        for theme, theme_sigs in themes_map.items():
            theme_sigs_sorted = sorted(
                theme_sigs,
                key=lambda s: priority_order.get(s.get("priority", "low"), 3),
            )
            themes.append({
                "theme": theme,
                "count": len(theme_sigs),
                "signals": theme_sigs_sorted,
            })

        # 按信号数量排序
        themes.sort(key=lambda t: t["count"], reverse=True)
        return themes

    def _clean_md(self, text: str) -> str:
        """清理 markdown 格式"""
        if not text:
            return ""
        text = re.sub(r'\*\*|__|\*|_', '', text)
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[-•]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{2,}', ' ', text)
        text = re.sub(r'\n', ' ', text)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    def _build_report_lines(
        self,
        track_id: str,
        track_name: str,
        report_date: str,
        all_signals: List[Dict],
        sorted_signals: List[Dict],
        by_type: Dict[str, list],
        themes: List[dict],
        merged: List[dict],
    ) -> List[str]:
        """构建报告正文"""
        total = len(all_signals)
        high_count = sum(1 for s in all_signals if s.get("priority") == "high")
        merged_count = len(merged)

        lines = [
            f"📊 {track_name} — 投资雷达日报",
            f"{report_date}" + (f" （含前{merged_count}日合并信号）" if merged_count else ""),
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"【今日概况】共捕获 {total} 个信号，高优先级 {high_count} 个",
            "",
        ]

        # 主题分组展示
        if themes:
            lines.append("【主题分布】")
            for t in themes[:5]:
                lines.append(f"  • {t['theme']}: {t['count']} 个")
            lines.append("")

        # 高优先级信号
        high_priority = [s for s in sorted_signals if s.get("priority") == "high"]
        if high_priority:
            lines.append("🔥 高优先级信号:")
            for sig in high_priority[:5]:
                title = self._clean_md(
                    sig.get("full_name") or sig.get("title", "")
                )
                content = self._clean_md(sig.get("content", "")[:100])
                sig_type = sig.get("type") or sig.get("signal_type", "") or "unknown"
                lines.append(f"  ◆ [{sig_type}] {title}")
                if content:
                    lines.append(f"    {content}")
                lines.append("")

        # 融资/投资动态（重点展示）
        funding_sigs = (
            by_type.get("funding_news", [])
            + by_type.get("itjuzi_funding", [])
        )
        if funding_sigs:
            lines.append("💰 融资动态:")
            for sig in funding_sigs[:3]:
                title = self._clean_md(
                    sig.get("full_name") or sig.get("title", "")
                )
                content = self._clean_md(sig.get("content", "")[:120])
                lines.append(f"  • {title}")
                if content:
                    lines.append(f"    {content}")
            lines.append("")

        # GitHub / HN 热点
        hot_sigs = (
            by_type.get("star_surge", [])
            + by_type.get("hackernews_hot", [])
        )
        if hot_sigs:
            lines.append("📈 技术热点:")
            for sig in hot_sigs[:3]:
                title = self._clean_md(
                    sig.get("full_name") or sig.get("title", "")
                )
                score_info = ""
                if sig.get("score"):
                    score_info = f" (HN Score: {sig['score']})"
                elif sig.get("stars"):
                    score_info = f" (⭐{sig['stars']})"
                lines.append(f"  • {title}{score_info}")
            lines.append("")

        # 论文/专利趋势
        research_sigs = (
            by_type.get("paper_burst", [])
            + by_type.get("patent_trend", [])
        )
        if research_sigs:
            lines.append("📚 学术/专利:")
            for sig in research_sigs[:3]:
                title = self._clean_md(
                    sig.get("full_name") or sig.get("title", "")
                )
                lines.append(f"  • {title[:80]}")
            lines.append("")

        # 国际动态
        intl_sigs = by_type.get("techcrunch_news", [])
        if intl_sigs:
            lines.append("🌍 国际动态:")
            for sig in intl_sigs[:2]:
                title = self._clean_md(
                    sig.get("full_name") or sig.get("title", "")
                )
                lines.append(f"  • {title[:80]}")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"📅 报告生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "投资雷达 · Premium专属",
        ])

        return lines

    def batch_generate(
        self,
        reports: List[dict],
    ) -> List[dict]:
        """
        批量生成多赛道报告

        Args:
            reports: [
                {"track_id": str, "track_name": str, "signals": [...]},
                ...
            ]

        Returns:
            生成结果列表
        """
        results = []
        for r in reports:
            result = self.generate(
                track_id=r["track_id"],
                track_name=r["track_name"],
                signals=r.get("signals", []),
                report_date=r.get("date"),
                merged_signals=r.get("merged_signals"),
                is_silent=r.get("is_silent", False),
            )
            results.append(result)
        return results
