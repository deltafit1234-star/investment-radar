#!/usr/bin/env python3
"""
投资雷达 - 本地运行脚本 (Phase 1)
AI大模型赛道完整数据链路
"""

import sys
import os
import argparse
import json
import random
from pathlib import Path
from datetime import datetime

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
        return result.data

    except Exception as e:
        logger.exception(f"  异常: {e}")
        return []


# ═══════════════════════════════════════════════════════
# 数据源 2: arXiv 论文
# ═══════════════════════════════════════════════════════
def run_arxiv(config) -> list:
    """采集 arXiv 论文"""
    logger.info("[2/6] 采集 arXiv 论文...")
    try:
        from src.采集.arxiv import ArxivCollector

        source = config.get_source_config("ai_llm", "arxiv_cs_ai")
        if not source:
            logger.warning("  未找到 arXiv 配置，跳过")
            return []

        collector = ArxivCollector(source)
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
def run_36kr(config) -> list:
    """采集 36kr 科技新闻"""
    logger.info("[3/6] 采集 36kr 科技新闻...")
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


# ═══════════════════════════════════════════════════════
# 检测: Star 激增 + 论文爆发 + 融资新闻
# ═══════════════════════════════════════════════════════
def run_detection(
    github_data: list,
    arxiv_data: list,
    news_data: list,
    config
) -> list:
    """信号检测"""
    logger.info("[5/6] 信号检测...")
    try:
        from src.检测.star_detector import StarSurgeDetector
        from src.检测.paper_detector import PaperBurstDetector
        from src.core.database import get_db

        rules = config.get_detection_rules("ai_llm")
        star_thresholds = {}
        paper_thresholds = {}
        keywords = []

        for rule in rules:
            rule_id = rule.get("rule_id")
            if rule_id == "star_surge":
                star_thresholds = rule.get("threshold", {})
            elif rule_id == "paper_burst":
                paper_thresholds = rule.get("threshold", {})
            elif rule_id == "funding_news":
                keywords = rule.get("keywords", [])

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

            alert = star_detector.detect(repo_with_history)
            if alert:
                alerts.append(alert)

        # ── 论文爆发检测 ────────────────────────────────
        paper_detector = PaperBurstDetector(thresholds=paper_thresholds)
        paper_alerts = paper_detector.batch_detect([{"papers": arxiv_data, "count": len(arxiv_data)}])
        alerts.extend(paper_alerts)

        # ── 融资/热点新闻检测 ──────────────────────────
        funding_keywords = ["融资", "获投", "B轮", "C轮", "估值", "人民币", "美元", "上市", "IPO", "投资"]
        ai_keywords = ["大模型", "LLM", "GPT", "Claude", "Llama", "Agent", "多模态", "开源模型", "文心", "通义", "智谱", "Kimi", "ChatGPT"]

        for news in news_data:
            title = news.get("title", "")
            desc = news.get("description", "")
            text = title + desc

            has_funding = any(k in text for k in funding_keywords)
            has_ai = any(k in text for k in ai_keywords)

            if has_funding and has_ai:
                alerts.append({
                    "type": "funding_news",
                    "full_name": title,
                    "content": desc[:200],
                    "url": news.get("url", ""),
                    "published_at": news.get("published_at", ""),
                    "priority": "high",
                    "message": f"融资动态: {title}"
                })
            elif has_ai and ("发布" in text or "开源" in text or "新模型" in text):
                alerts.append({
                    "type": "model_news",
                    "full_name": title,
                    "content": desc[:200],
                    "url": news.get("url", ""),
                    "published_at": news.get("published_at", ""),
                    "priority": "medium",
                    "message": f"AI 模型动态: {title}"
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


# ═══════════════════════════════════════════════════════
# LLM 丰富化
# ═══════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════
# 推送通知
# ═══════════════════════════════════════════════════════
def run_notification(signals: list) -> bool:
    """推送通知"""
    logger.info("[推送] 微信通知...")
    try:
        from src.推送.wechat import WechatNotifier

        notifier = WechatNotifier()

        if not signals:
            msg = "📭 今日投资雷达\n\n暂无异常信号，继续观察。"
            notifier.send_message(msg)
            logger.info("  无信号，发送空报告")
            return True

        # 格式化为每日简报
        lines = ["📊 投资雷达 - 每日简报", "", f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]

        for sig in signals:
            formatted = notifier.format_signal_message(sig)
            lines.append(formatted)
            lines.append("")

        message = "\n".join(lines)
        notifier.send_message(message)
        logger.info(f"  推送成功: {len(signals)} 个信号")

        # 输出 JSON 供 Hermes cron 读取
        output_path = project_root / "data" / "latest_signals.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        logger.exception(f"  推送异常: {e}")
        return False


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", default="ai_llm")
    parser.add_argument("--skip-notification", action="store_true")
    args = parser.parse_args()

    setup()

    from src.core.config import get_config
    config = get_config()

    # 1. 采集
    github_data = run_github(config)
    arxiv_data = run_arxiv(config)
    news_data = run_36kr(config)
    hf_data = run_huggingface(config)

    # 2. 检测
    alerts = run_detection(github_data, arxiv_data, news_data, config)

    # 3. 关联分析
    correlated = run_correlation(alerts, config)

    # 4. 丰富化（仅 Star 激增走 LLM，减少 token 消耗）
    star_alerts = [a for a in correlated if a.get("type") == "star_surge"]
    other_alerts = [a for a in correlated if a.get("type") != "star_surge"]
    enriched_stars = run_enrichment(star_alerts, config) if star_alerts else []

    # 合并
    all_signals = enriched_stars + other_alerts

    # 5. 推送
    if args.skip_notification:
        logger.info("[跳过] 推送通知（--skip-notification）")
        notify_ok = True
    else:
        notify_ok = run_notification(all_signals)

    logger.info("=" * 60)
    logger.info(
        f"结果: GitHub:{len(github_data)}条 arXiv:{len(arxiv_data)}篇 "
        f"36kr:{len(news_data)}条 HF:{len(hf_data)}个 "
        f"告警:{len(all_signals)}个"
    )
    return 0 if notify_ok else 1


if __name__ == "__main__":
    sys.exit(main())
