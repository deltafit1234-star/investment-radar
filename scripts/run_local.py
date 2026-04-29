#!/usr/bin/env python3
"""
投资雷达 - 本地运行脚本 (Phase 1 + 2 ProtoType)
AI大模型赛道完整数据链路 + 每日情报报告（新数据源）
"""

import sys
import os
import argparse
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

# 加载 .env 环境变量
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level}: {message}",
    level="INFO"
)


def setup():
    logger.info("=" * 60)
    logger.info("投资雷达 - Phase 1")
    logger.info("=" * 60)
    (project_root / "data").mkdir(exist_ok=True)
    (project_root / "logs").mkdir(exist_ok=True)

    # 初始化数据库
    from src.core.database import init_db
    init_db()


# ═══════════════════════════════════════════════════════
# 数据源 1: GitHub Trending + Star History
# ═══════════════════════════════════════════════════════
def run_github(config) -> list:
    """采集 GitHub Trending + 记录 Star 历史"""
    logger.info("[1/6] 采集 GitHub Trending...")
    try:
        from src.采集.github import GitHubCollector
        from src.core.database import get_db

        source = config.get_source_config("ai_llm", "github_trending")
        if not source:
            logger.error("  未找到 GitHub 配置")
            return []

        collector = GitHubCollector(source)
        result = collector.run()

        if not result.success:
            logger.error(f"  失败: {result.error}")
            return []

        logger.info(f"  成功: {result.total_count} 条数据")

        # 记录 Star 快照到数据库
        db = get_db()
        saved_count = 0
        for i, repo in enumerate(result.data):
            full_name = repo.get("full_name", "")
            if "/" not in full_name:
                continue
            owner, repo_name = full_name.split("/", 1)
            stars = repo.get("stars", 0)
            try:
                db.save_star_snapshot(owner, repo_name, stars, rank=i + 1)
                saved_count += 1
            except Exception:
                pass  # 忽略重复插入错误

        if saved_count:
            logger.info(f"  Star 历史已记录: {saved_count} 个项目")

        # 保存每日 Trending 归档（包含完整排名）
        archive_date = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            archive_count = db.save_trending_archive(result.data, archive_date)
            logger.info(f"  Trending 归档已保存: {archive_date} - {archive_count} 条")
        except Exception as e:
            logger.warning(f"  Trending 归档保存失败: {e}")

        return result.data

    except Exception as e:
        logger.exception(f"  异常: {e}")
        return []


# ═══════════════════════════════════════════════════════
# 数据源 2: arXiv 论文
# ═══════════════════════════════════════════════════════
def run_arxiv(config, track_id: str = "ai_llm") -> list:
    """采集 arXiv 论文（混合模式：优先 API，429 时自动降级到 RSS）

    Args:
        config: 全局配置对象
        track_id: 赛道ID，用于获取对应的 arXiv 分类配置
    """
    logger.info(f"[2/6] 采集 arXiv 论文（{track_id}，混合模式）...")
    try:
        # 使用混合采集器：API 优先，失败时自动降级到 RSS
        from src.采集.arxiv_rss import ArxivHybridCollector

        # 动态获取该赛道的 arXiv source
        source = config.get_source_config(track_id, f"{track_id}_arxiv")
        if not source:
            # 降级：尝试通用 arxiv_cs_ai
            source = config.get_source_config(track_id, "arxiv_cs_ai")
        if not source:
            logger.warning(f"  未找到 {track_id} 的 arXiv 配置，跳过")
            return []

        collector = ArxivHybridCollector(source)
        result = collector.run()

        if result.success:
            logger.info(f"  成功: {result.total_count} 篇论文")
            return result.data or []
        else:
            logger.warning(f"  arXiv 失败: {result.error}")
            return []
    except Exception as e:
        logger.warning(f"  arXiv 异常: {e}")
        return []


# ═══════════════════════════════════════════════════════
# 数据源 3: 36kr 新闻
# ═══════════════════════════════════════════════════════
def run_36kr(config, track_id: str = "ai_llm") -> list:
    """采集 36kr 科技新闻（按赛道关键词过滤）

    Args:
        config: 全局配置对象
        track_id: 赛道ID
    """
    logger.info(f"[3/6] 采集 36kr 科技新闻（{track_id}）...")
    try:
        from src.采集.news_36kr import News36krCollector

        source = config.get_source_config("ai_llm", "36kr_tech")
        if not source:
            logger.warning("  未找到 36kr 配置，跳过")
            return []

        collector = News36krCollector(source)
        result = collector.run()

        if result.success:
            logger.info(f"  成功: {result.total_count} 条新闻")
            return result.data or []
        else:
            logger.warning(f"  36kr 失败: {result.error}")
            return []
    except Exception as e:
        logger.warning(f"  36kr 异常: {e}")
        return []


# ═══════════════════════════════════════════════════════
# 数据源 4: HuggingFace Models（网络不可达时跳过）
# ═══════════════════════════════════════════════════════
def run_huggingface(config) -> list:
    """采集 HuggingFace 热门模型"""
    logger.info("[4/6] 采集 HuggingFace Models...")
    try:
        import requests
        # 先做网络探测
        try:
            requests.get("https://huggingface.co", timeout=5)
        except Exception:
            logger.warning("  HuggingFace 网络不可达，跳过（Phase 1 可选）")
            return []

        from src.采集.huggingface import HuggingFaceCollector

        source = config.get_source_config("ai_llm", "huggingface_models")
        if not source:
            logger.warning("  未找到 HuggingFace 配置，跳过")
            return []

        collector = HuggingFaceCollector(source)
        result = collector.run()

        if result.success:
            logger.info(f"  成功: {result.total_count} 个模型")
            return result.data or []
        else:
            logger.warning(f"  HuggingFace 失败: {result.error}")
            return []
    except Exception as e:
        logger.warning(f"  HuggingFace 异常: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# 数据源 5: Google Patents（新增 - Phase 2 ProtoType）
# ═══════════════════════════════════════════════════════════════════
def run_google_patents(config, track_id: str = "ai_llm") -> list:
    """采集 Google Patents 专利趋势（按赛道关键词搜索）"""
    logger.info(f"[5/N] 采集 Google Patents（{track_id}）...")
    try:
        from src.采集.google_patents import GooglePatentsCollector

        source = config.get_source_config(track_id, "google_patents")
        if not source:
            logger.warning(f"  未找到 {track_id} 的 Google Patents 配置，跳过")
            return []

        collector = GooglePatentsCollector(source)
        result = collector.run()

        if result.success:
            logger.info(f"  成功: {result.total_count} 条专利")
            return result.data or []
        else:
            logger.warning(f"  Google Patents 失败: {result.error}")
            return []
    except Exception as e:
        logger.warning(f"  Google Patents 异常: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# 数据源 6: TechCrunch RSS（新增 - Phase 2 ProtoType）
# ═══════════════════════════════════════════════════════════════════
def run_techcrunch(config, track_id: str = "ai_llm") -> list:
    """采集 TechCrunch 国际科技新闻（按赛道关键词过滤）"""
    logger.info(f"[6/N] 采集 TechCrunch RSS（{track_id}）...")
    try:
        from src.采集.techcrunch import TechCrunchCollector

        collector = TechCrunchCollector()
        result = collector.run()

        if result.success:
            logger.info(f"  成功: {result.total_count} 条新闻")
            return result.data or []
        else:
            logger.warning(f"  TechCrunch 失败: {result.error}")
            return []
    except Exception as e:
        logger.warning(f"  TechCrunch 异常: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# 数据源 8: IT桔子融资爬虫（新增 - Phase 2 ProtoType）
# ═══════════════════════════════════════════════════════════════════
def run_itjuzi(config, track_id: str = "ai_llm") -> list:
    """采集 IT桔子 国内融资事件（爬虫原型）"""
    logger.info(f"[8/N] 采集 IT桔子（{track_id}）...")
    try:
        from src.采集.itjuzi import ItjuziFundingCollector

        collector = ItjuziFundingCollector()
        # 按赛道关键词搜索
        keywords = _get_track_keywords(track_id, config)
        results = []
        for kw in keywords[:3]:  # 最多试3个关键词
            result = collector.collect(kw)
            if result.success:
                results.extend(result.data or [])
        logger.info(f"  成功: {len(results)} 条融资事件")
        return results
    except Exception as e:
        logger.warning(f"  IT桔子异常: {e}")
        return []


def _get_track_keywords(track_id: str, config) -> list:
    """从赛道配置中获取关键词列表"""
    try:
        from src.core.track_loader import get_enabled_tracks
        tracks = get_enabled_tracks()
        for t in tracks:
            if t.get("track_id") == track_id:
                return t.get("keywords", [])
    except Exception:
        pass
    return []


# ═══════════════════════════════════════════════════════════════════
# 数据源 7: Hacker News API（新增 - Phase 2 ProtoType）
# ═══════════════════════════════════════════════════════════════════
def run_hackernews(config, track_id: str = "ai_llm") -> list:
    """采集 Hacker News 社区热点（按赛道关键词过滤）"""
    logger.info(f"[7/N] 采集 Hacker News（{track_id}）...")
    try:
        from src.采集.hackernews import HackerNewsCollector

        collector = HackerNewsCollector()
        result = collector.run()

        if result.success:
            logger.info(f"  成功: {result.total_count} 条热点")
            return result.data or []
        else:
            logger.warning(f"  Hacker News 失败: {result.error}")
            return []
    except Exception as e:
        logger.warning(f"  Hacker News 异常: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# 检测: Star 激增 + 论文爆发 + 融资新闻 + 新数据源信号
# ═══════════════════════════════════════════════════════════════
def run_detection(
    github_data: list,
    arxiv_data: list,
    news_data: list,
    patents_data: list,
    techcrunch_data: list,
    hn_data: list,
    itjuzi_data: list,
    config,
    track_id: str = "ai_llm"
) -> list:
    """信号检测（支持多赛道）

    Args:
        github_data: GitHub Trending 数据（所有赛道共用）
        arxiv_data: 当前赛道的 arXiv 论文
        news_data: 当前赛道的新闻数据
        patents_data: Google Patents 专利数据
        techcrunch_data: TechCrunch 新闻数据
        hn_data: Hacker News 热点数据
        itjuzi_data: IT桔子 融资事件数据
        config: 全局配置
        track_id: 赛道ID，用于加载赛道专属规则
    """
    logger.info("[信号检测] ...")
    try:
        from src.检测.star_detector import StarSurgeDetector
        from src.检测.paper_detector import PaperBurstDetector
        from src.core.database import get_db

        # ── 辅助函数 ────────────────────────────────
        def _extract_company_name(title: str) -> str:
            """从标题提取公司名（取前15字作为去重键）"""
            return title[:15].strip(":-：· ")

        def _extract_round_type(text: str) -> str:
            """提取融资轮次"""
            for kw in ["天使轮", "A轮", "B轮", "C轮", "D轮", "Pre-A", "Pre-B"]:
                if kw in text:
                    return kw
            return "未知轮次"
        # ─────────────────────────────────────────

        rules = config.get_detection_rules(track_id)
        star_thresholds = {}
        paper_thresholds = {}
        paper_keywords = []
        funding_keywords_cfg = []

        for rule in rules:
            rule_id = rule.get("rule_id")
            if rule_id == "star_surge":
                star_thresholds = rule.get("threshold", {})
            elif rule_id == "paper_burst":
                paper_thresholds = rule.get("threshold", {})
                paper_keywords = rule.get("keywords", [])
            elif rule_id == "funding_news":
                funding_keywords_cfg = rule.get("keywords", [])

        alerts = []

        # ── Star 激增检测 ───────────────────────────────
        star_detector = StarSurgeDetector(thresholds=star_thresholds)
        db = get_db()

        for repo in github_data[:15]:
            full_name = repo.get("full_name", "")
            if "/" not in full_name:
                continue
            owner, repo_name = full_name.split("/", 1)
            stars = repo.get("stars", 0)

            # 查询历史快照（24小时前）
            prev = db.get_previous_stars(owner, repo_name, hours=24)
            repo_with_history = repo.copy()

            if prev:
                repo_with_history["stars_previous"] = prev.stars
            else:
                # 无历史时，模拟一个合理增长（仅用于演示）
                repo_with_history["stars_previous"] = int(stars / random.uniform(1.2, 1.8))

            # 查询 Trending 归档：近 30 天有多少天上榜
            trend_days = db.get_repo_trend_days(owner, repo_name, days=30)
            repo_with_history["trend_days"] = trend_days

            alert = star_detector.detect(repo_with_history)
            if alert:
                # 上榜天数 >= 7天 → 可信度高，提升优先级
                if trend_days >= 7:
                    alert["priority"] = "high"
                    alert["consistency_note"] = f"连续上榜 {trend_days} 天，可信信号"
                alerts.append(alert)

        # ── 论文爆发检测（赛道专属关键词）──────────────
        paper_detector = PaperBurstDetector(
            thresholds=paper_thresholds,
            keywords=paper_keywords if paper_keywords else None
        )
        paper_alerts = paper_detector.batch_detect([{"papers": arxiv_data, "count": len(arxiv_data)}])
        alerts.extend(paper_alerts)

        # ── 融资/热点新闻检测（增强版）───────────────
        # 通用关键词 + 赛道专属关键词（合并去重）
        _base_funding = ["融资", "获投", "B轮", "C轮", "估值", "人民币", "美元", "上市", "IPO", "投资", "天使轮", "A轮", "D轮"]
        _base_ai = ["大模型", "LLM", "GPT", "Claude", "Llama", "Agent", "多模态", "开源模型", "文心", "通义", "智谱", "Kimi", "ChatGPT", "Sora", "GPT-4", "Gemini", "Mistral", "Grok"]
        # 从 track config 的 funding_news rule 补充赛道专属关键词
        funding_keywords = list(set(_base_funding + funding_keywords_cfg))
        ai_keywords = list(set(_base_ai + funding_keywords_cfg))
        # 知名 VC 白名单——出现在融资新闻中 = 高可信度
        vc_whitelist = [
            "红杉", "高瓴", "IDG", "经纬", "真格", "创新工场", "GGV",
            "SIG", "源码", "线性", "明势", "BAI", "纪源",
            "腾讯", "阿里", "字节", "小米", "京东", "美团",
            "深创投", "国投", "招银", "中金", "顺为",
            "Qiming", "Shunwei", "Hillhouse", "Sequoia", "IDG Capital",
        ]

        seen_funding = {}  # 去重：{(公司名关键词, 融资轮次): alert}
        seen_model_news = set()  # 去重：(标题前30字)

        for news in news_data:
            title = news.get("title", "")
            desc = news.get("description", "")
            text = title + desc

            has_funding = any(k in text for k in funding_keywords)
            has_ai = any(k in text for k in ai_keywords)

            # ── 融资新闻 ──────────────────────────────
            if has_funding and has_ai:
                # 去重：公司名 + 轮次相同则跳过（保留第一条）
                # 提取公司名（标题中第一个 AI 相关关键词前的内容）
                company = _extract_company_name(title)
                round_type = _extract_round_type(text)
                dedup_key = (company, round_type)
                if dedup_key in seen_funding:
                    logger.debug(f"  跳过重复融资: {title[:40]}...")
                    continue
                seen_funding[dedup_key] = True

                # VC 加权：检查是否有知名机构
                vc_found = [vc for vc in vc_whitelist if vc in text]
                priority = "high"
                vc_note = ""
                if vc_found:
                    priority = "high"
                    vc_note = f"【{', '.join(vc_found)} 参投】"
                elif "亿" in text or "千万" in text:
                    priority = "medium"  # 有金额但无知名VC

                alerts.append({
                    "type": "funding_news",
                    "full_name": title,
                    "content": f"{vc_note}{desc[:200]}".strip(),
                    "url": news.get("url", ""),
                    "published_at": news.get("published_at", ""),
                    "priority": priority,
                    "message": f"融资动态: {title}",
                    "vc_found": vc_found,
                })

            # ── 纯模型动态（无融资）────────────────
            elif has_ai and ("发布" in text or "开源" in text or "新模型" in text or "重磅" in text):
                # 去重：标题前30字相同跳过
                title_key = title[:30]
                if title_key in seen_model_news:
                    continue
                seen_model_news.add(title_key)

                # 知名公司/项目发布 → medium，否则 low
                notable = any(n in title for n in ["OpenAI", "Anthropic", "Google", "Meta", "DeepSeek", "Mistral", "Llama", "通义", "文心", "智谱", "Kimi", "ChatGPT"])
                priority = "medium" if notable else "low"

                alerts.append({
                    "type": "model_news",
                    "full_name": title,
                    "content": desc[:200],
                    "url": news.get("url", ""),
                    "published_at": news.get("published_at", ""),
                    "priority": priority,
                    "message": f"AI 模型动态: {title}",
                })

        # ── Google Patents 专利趋势信号 ─────────────────
        for patent in patents_data:
            title = patent.get("title", "")
            applicant = patent.get("applicant", "")
            patent_number = patent.get("patent_number", "")
            abstract = patent.get("abstract", "")
            url = patent.get("url", "")
            date_str = patent.get("date", "")

            # 专利 = 技术热点信号（申请人含知名公司更可信）
            notable_companies = [
                "Google", "Meta", "Microsoft", "Apple", "Amazon", "Nvidia",
                "Intel", "AMD", "Tesla", "OpenAI", "Anthropic", "ByteDance",
                "Alibaba", "Tencent", "Baidu", "Huawei", "ByteDance",
            ]
            is_notable = any(c in applicant for c in notable_companies)
            priority = "medium" if is_notable else "low"

            alerts.append({
                "type": "patent_trend",
                "full_name": title,
                "content": f"申请人: {applicant} | 专利号: {patent_number} | {abstract[:150]}".strip(),
                "url": url,
                "published_at": date_str,
                "priority": priority,
                "message": f"专利趋势: {title}",
                "applicant": applicant,
            })

        # ── TechCrunch 国际科技新闻信号 ────────────────
        for article in techcrunch_data:
            title = article.get("title", "")
            summary = article.get("summary", "")
            link = article.get("link", "")
            published = article.get("published", "")
            categories = article.get("categories", [])

            # TechCrunch 新闻质量较高，知名公司/大额融资直接给 high
            notable = any(
                n in title
                for n in [
                    "OpenAI", "Anthropic", "Google", "Meta", "Microsoft",
                    "Tesla", "SpaceX", "Stripe", "Databricks", "Scale AI",
                ]
            )
            has_funding = any(k in title + summary for k in ["raises", "funding", "round", "Series", "$"])
            priority = "high" if (has_funding or notable) else "medium"

            alerts.append({
                "type": "techcrunch_news",
                "full_name": title,
                "content": summary[:200],
                "url": link,
                "published_at": published,
                "priority": priority,
                "message": f"国际科技: {title}",
                "categories": categories,
            })

        # ── Hacker News 社区热点信号 ────────────────────
        for story in hn_data:
            title = story.get("title", "")
            score = story.get("score", 0)
            url = story.get("url", "")
            time_str = story.get("time", "")
            descendants = story.get("descendants", 0)
            hn_by = story.get("by", "")

            # HN 分数 > 200 = 强热点；> 100 = 中等；< 100 = 低
            if score >= 200:
                priority = "high"
            elif score >= 100:
                priority = "medium"
            else:
                priority = "low"

            alerts.append({
                "type": "hackernews_hot",
                "full_name": title,
                "content": f"HN Score: {score} | Comments: {descendants} | Posted by {hn_by}",
                "url": url,
                "published_at": time_str,
                "priority": priority,
                "message": f"HN 热点: {title}",
                "score": score,
            })

        # ── IT桔子 融资事件信号 ────────────────────────
        for event in itjuzi_data:
            company = event.get("company_name", "")
            round_type = event.get("round", "未知轮次")
            amount = event.get("amount", "")
            investors = event.get("investors", "")
            date_str = event.get("date", "")
            tags = event.get("tags", [])

            # IT桔子融资 = 高可信度信号
            priority = "high"
            if "天使" in round_type or "种子" in round_type:
                priority = "medium"

            alerts.append({
                "type": "itjuzi_funding",
                "full_name": f"{company} {round_type}",
                "content": f"轮次: {round_type} | 金额: {amount} | 投资方: {investors}",
                "url": "",
                "published_at": date_str,
                "priority": priority,
                "message": f"融资: {company}完成{round_type}",
                "company": company,
                "round": round_type,
                "amount": amount,
                "investors": investors,
                "tags": tags,
            })

        logger.info(f"  检测到 {len(alerts)} 个告警")
        return alerts

    except Exception as e:
        logger.exception(f"  检测异常: {e}")
        return []


# ═══════════════════════════════════════════════════════
# 关联分析
# ═══════════════════════════════════════════════════════
def run_correlation(alerts: list, config) -> list:
    """关联分析：多个信号源同时触发 = 高置信度信号"""
    logger.info("[6/6] 关联分析...")
    try:
        # 按类型分组
        by_type = {}
        for a in alerts:
            t = a.get("type", "unknown")
            by_type.setdefault(t, []).append(a)

        correlated = []

        for alert in alerts:
            alert = alert.copy()
            correlation_notes = []

            # 规则1: Star 激增 + 论文爆发 + 新闻 → 强信号
            has_star = "star_surge" in by_type
            has_paper = "paper_burst" in by_type
            has_news = "funding_news" in by_type or "model_news" in by_type

            if has_star and has_paper:
                correlation_notes.append("GitHub Star 增长与论文爆发同时出现")
            if has_news and has_star:
                correlation_notes.append("融资/模型新闻与 GitHub 热度上升关联")
            if has_news and has_paper:
                correlation_notes.append("融资新闻与学术研究热度关联")

            if correlation_notes:
                alert["correlation"] = " | ".join(correlation_notes)
                alert["priority"] = "high"  # 提升优先级

            correlated.append(alert)

        if any("correlation" in a for a in correlated):
            logger.info(f"  关联出 {sum(1 for a in correlated if 'correlation' in a)} 个高置信度信号")

        return correlated

    except Exception as e:
        logger.warning(f"  关联分析异常: {e}")
        return alerts


# ═══════════════════════════════════════════════════════════════
# Premium 深度分析
# ═══════════════════════════════════════════════════════════════
def _update_signal_premium_analysis(db, sig: dict, sig_data: dict,
                                     track_cfg: dict, tenant_ids: list):
    """
    检查是否有 Premium 租户订阅了该信号，若有则生成深度分析并更新数据库。
    """
    try:
        from src.core.database import TenantSubscription

        session = db.get_session()
        try:
            premium_subs = session.query(TenantSubscription).filter(
                TenantSubscription.tenant_id.in_(tenant_ids),
                TenantSubscription.track_id == track_cfg["track_id"],
                TenantSubscription.plan == "premium",
                TenantSubscription.enabled == True,
            ).all()

            has_premium_subscriber = len(premium_subs) > 0

            from src.core.database import Signal
            signal_record = session.query(Signal).filter(
                Signal.track_id == sig_data["track_id"],
                Signal.source_id == sig_data["source_id"],
                Signal.title == sig_data["title"],
            ).order_by(Signal.created_at.desc()).first()

            if not signal_record:
                return

            if not signal_record.has_premium_content:
                signal_record.ad_space = _generate_ad_space(track_cfg)

            if has_premium_subscriber and not signal_record.analysis_premium:
                logger.info(f"  [Premium] 深度分析: {sig_data['title'][:40]}")
                from src.分析.deep_analyzer import DeepAnalyzer
                analyzer = DeepAnalyzer()
                enriched = analyzer.analyze(sig, track_cfg)
                signal_record.analysis_premium = enriched.get("analysis_premium")
                signal_record.has_premium_content = True
            elif signal_record.analysis_premium:
                signal_record.has_premium_content = True

            session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"  Premium 分析异常: {e}")


def _generate_ad_space(track_cfg: dict) -> str:
    track_name = track_cfg.get("track_name", track_cfg.get("track_id", ""))
    return (
        f"📈 【{track_name}】深度分析仅对 Premium 租户开放\n"
        f"升级 Premium 获取：投资机会解读 / 竞争格局分析 / 风险提示 / 相关公司\n"
        f"联系我们升级账号 →"
    )


# ═══════════════════════════════════════════════════════════════
# LLM 丰富化

def run_enrichment(signals: list, config) -> list:
    """LLM 信号丰富化"""
    logger.info("[LLM] 信号丰富化...")
    try:
        from src.分析.enricher import SignalEnricher

        llm_cfg = config.llm_config
        enricher = SignalEnricher(llm_config=llm_cfg)

        enriched = enricher.batch_enrich(signals)
        logger.info(f"  丰富化完成: {len(enriched)} 个信号")
        return enriched
    except Exception as e:
        logger.exception(f"  丰富化异常: {e}")
        return signals


# ═══════════════════════════════════════════════════════════════════
# 推送通知（多租户路由）
# ═══════════════════════════════════════════════════════════════════
def run_notification(signals: list, target: Optional[str] = None) -> bool:
    """
    推送通知（多租户版本）

    策略：
    - 有显式 target → 直接发给指定群（现有行为，兼容单租户）
    - 无 target → 通过 NotificationRouter 按租户配置分群推送
    """
    logger.info("[推送] 微信通知（多租户路由）...")
    try:
        from src.推送.wechat import WechatNotifier
        from src.推送.router import NotificationRouter

        # 显式指定了 target → 直接发（单租户兼容）
        if target:
            return _send_direct_wechat(signals, target)

        # 多租户路由推送
        if not signals:
            # 无信号时，仍尝试通知已订阅租户（发空报告）
            logger.info("  无信号，跳过多租户推送")
            return True

        router = NotificationRouter()
        result = router.route_signals(signals)

        reached = result.get("tenants_reached", 0)
        details = result.get("details", [])
        ok_count = sum(1 for d in details if d.get("ok"))
        logger.info(f"  多租户推送完成: {reached} 个租户, {ok_count}/{len(details)} 成功")

        # 同时保存到 JSON 供 cron 读取
        output_path = project_root / "data" / "latest_signals.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2)

        return result.get("success", True)

    except Exception as e:
        logger.exception(f"  推送异常: {e}")
        return False


def _send_direct_wechat(signals: list, target: str) -> bool:
    """直接微信推送（单租户兼容模式）"""
    try:
        from src.推送.wechat import WechatNotifier

        notifier = WechatNotifier()
        if not signals:
            msg = "📭 今日投资雷达\n\n暂无异常信号，继续观察。"
            notifier.send_message(msg, target=target)
            return True

        report_type = "周报" if "weekly" in str(target) else "简报"
        lines = [f"📊 投资雷达 - 每日{report_type}", "", f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]

        for sig in signals:
            formatted = notifier.format_signal_message(sig)
            lines.append(formatted)
            lines.append("")

        message = "\n".join(lines)
        notifier.send_message(message, target=target)

        # 保存 JSON
        output_path = project_root / "data" / "latest_signals.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2)

        logger.info(f"  推送成功: {len(signals)} 个信号 → {target}")
        return True
    except Exception as e:
        logger.exception(f"  直接推送异常: {e}")
        return False


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", default=None, help="指定运行单个赛道（如 ai_llm），默认运行所有赛道")
    parser.add_argument("--skip-notification", action="store_true")
    parser.add_argument("--weekly-report", action="store_true", help="生成周报而非日报")
    parser.add_argument("--week-start", default=None, help="周起始日期 YYYY-MM-DD")
    parser.add_argument("--deliver-to", default=None, help="推送目标，如 weixin:chat_id（支持分群推送）")
    args = parser.parse_args()

    setup()

    from src.core.config import get_config
    from src.core.track_loader import get_enabled_tracks
    config = get_config()

    # 周报模式：读取历史信号，生成周报
    if args.weekly_report:
        return generate_weekly_report(config, args.week_start, target=args.deliver_to)

    # 确定要运行的赛道
    if args.track:
        target_tracks = [t for t in get_enabled_tracks() if t["track_id"] == args.track]
        if not target_tracks:
            logger.error(f"未找到赛道或未启用: {args.track}")
            return 1
    else:
        target_tracks = get_enabled_tracks()

    logger.info(f"=" * 60)
    logger.info(f"投资雷达 -  {'单赛道: ' + args.track if args.track else '全赛道模式'} ({len(target_tracks)} 个赛道)")
    logger.info(f"赛道列表: {[t['track_id'] for t in target_tracks]}")
    logger.info(f"=" * 60)

    # 全局数据（所有赛道共用）
    github_data = run_github(config)  # GitHub trending 只采一次
    all_signals = []

    for track_cfg in target_tracks:
        track_id = track_cfg["track_id"]
        track_name = track_cfg.get("track_name", track_id)
        logger.info(f"\n{'='*40}\n  赛道: {track_name} ({track_id})\n{'='*40}")

        # 1. 采集（按赛道）
        arxiv_data = run_arxiv(config, track_id)
        news_data = run_36kr(config, track_id)
        hf_data = []  # HF 在 cron 环境不可达
        patents_data = run_google_patents(config, track_id)
        techcrunch_data = run_techcrunch(config, track_id)
        hn_data = run_hackernews(config, track_id)
        itjuzi_data = run_itjuzi(config, track_id)

        # 2. 检测（包含 IT桔子融资数据）
        alerts = run_detection(
            github_data, arxiv_data, news_data,
            patents_data, techcrunch_data, hn_data, itjuzi_data,
            config, track_id
        )

        # 2b. 专题分组（按主题归类信号）
        grouped_alerts = run_thematic_grouping(alerts, config, track_id)

        # 3. 关联分析
        correlated = run_correlation(grouped_alerts, config)

        # 4. 丰富化（仅 Star 激增走 LLM）
        star_alerts = [a for a in correlated if a.get("type") == "star_surge"]
        other_alerts = [a for a in correlated if a.get("type") != "star_surge"]
        enriched_stars = run_enrichment(star_alerts, config) if star_alerts else []
        track_signals = enriched_stars + other_alerts

        # 4b. 信号过滤（评分 + 静默日判断）
        filtered_signals = run_signal_filter(track_signals, config, track_id)

        # 标记赛道归属
        for sig in filtered_signals:
            sig["track_id"] = track_id
            sig["track_name"] = track_name

        logger.info(f"  赛道 {track_id}: 检测到 {len(filtered_signals)} 个信号")
        all_signals.extend(filtered_signals)

    # ── 全局存库 + 去重 ───────────────────────────
    try:
        from src.core.database import get_db
        db = get_db()
        saved = 0
        skipped = 0
        for sig in all_signals:
            title = (sig.get("full_name") or sig.get("title") or "")[:200]
            signal_type = sig.get("type", "unknown") or "unknown"
            track_id_sig = sig.get("track_id", "unknown")

            if title:
                dup = db.is_duplicate_signal(
                    track_id=track_id_sig,
                    signal_type=signal_type,
                    title=title,
                    days=7,
                    similarity_threshold=0.8,
                )
                if dup:
                    skipped += 1
                    continue

            try:
                from src.core.tenant_config import TenantConfigLoader

                # 填充 tenant_ids（所有订阅该赛道的活跃租户）
                sig_data = {
                    "track_id": track_id_sig,
                    "source_id": signal_type,
                    "signal_type": signal_type,
                    "title": title,
                    "content": sig.get("content") or sig.get("summary", ""),
                    "raw_data": sig,
                    "priority": sig.get("priority", "low"),
                    "meaning": sig.get("meaning", ""),
                }
                sig_data = TenantConfigLoader.fill_tenant_ids_for_signal(sig_data, track_id_sig)
                db.add_signal(sig_data)

                # ── Premium 深度分析（仅 Premium 租户订阅的信号）──────────
                tenant_ids = sig_data.get("tenant_ids", [])
                if tenant_ids:
                    _update_signal_premium_analysis(db, sig, sig_data, track_cfg, tenant_ids)

                # 同步回 all_signals 的原始 dict，这样 run_notification 能读到 tenant_ids
                sig["tenant_ids"] = tenant_ids
                saved += 1
            except Exception:
                pass
        logger.info(f"\n信号已存库: {saved} 条, 跳过重复: {skipped} 条")
    except Exception as e:
        logger.warning(f"  存DB异常: {e}")

    # ── 推送 ────────────────────────────────────
    if args.skip_notification:
        logger.info("[跳过] 推送通知（--skip-notification）")
        notify_ok = True
    else:
        notify_ok = run_notification(all_signals, target=args.deliver_to)

    logger.info("=" * 60)
    total_arxiv = sum(len(run_arxiv(config, t["track_id"]) or []) for t in target_tracks)
    logger.info(
        f"结果: GitHub:{len(github_data)}条 36kr:{sum(1 for s in all_signals)}条 "
        f"告警:{len(all_signals)}个"
    )
    return 0 if notify_ok else 1


def generate_weekly_report(config, week_start: str = None, target: str = None):
    """生成周报

    Args:
        config: 全局配置
        week_start: 周起始日期 YYYY-MM-DD
        target: 推送目标，如 weixin:chat_id
    """
    from src.分析.weekly_report import WeeklyReportGenerator
    from src.core.database import get_db

    logger.info("[周报] 生成中...")

    db = get_db()
    signals = db.get_signals(track_id="ai_llm", limit=200)

    # 过滤本周信号
    from datetime import datetime, timedelta
    if week_start:
        start_date = datetime.strptime(week_start, "%Y-%m-%d")
    else:
        today = datetime.now()
        start_date = today - timedelta(days=today.weekday())

    week_signals = [
        s.to_dict() for s in signals
        if s.created_at and s.created_at.replace(tzinfo=None) >= start_date.replace(tzinfo=None)
    ]

    logger.info(f"  本周信号数: {len(week_signals)}")

    # 生成报告
    generator = WeeklyReportGenerator(llm_config=config.llm_config)
    report = generator.generate(week_signals, week_start=week_start)

    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)

    # 保存到文件
    output_path = project_root / "data" / "weekly_report.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"  周报已保存: {output_path}")

    # 推送周报（分群推送支持）
    notify_ok = run_notification(
        [{"type": "weekly_report", "title": "投资雷达 - 本周周报", "content": report, "priority": "medium"}],
        target=target,
    )
    return 0 if notify_ok else 1


if __name__ == "__main__":
    sys.exit(main())
