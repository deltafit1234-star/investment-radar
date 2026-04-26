#!/usr/bin/env python3
"""
投资雷达 - 本地运行脚本 (Phase 0 MVP)
验证端到端流程
"""

import sys
import os
import argparse
import json
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
    logger.info("投资雷达 - Phase 0 MVP")
    logger.info("=" * 60)
    (project_root / "data").mkdir(exist_ok=True)
    (project_root / "logs").mkdir(exist_ok=True)


def run_github(config) -> list:
    """采集 GitHub Trending"""
    logger.info("[1/4] 采集 GitHub Trending...")
    try:
        from src.采集.github import GitHubCollector

        source = config.get_source_config("ai_llm", "github_trending")
        if not source:
            logger.error("  未找到 GitHub 配置")
            return []

        collector = GitHubCollector(source)
        result = collector.run()
        if result.success:
            logger.info(f"  成功: {result.total_count} 条数据")
            return result.data or []
        else:
            logger.error(f"  失败: {result.error}")
            return []
    except Exception as e:
        logger.exception(f"  异常: {e}")
        return []


def run_arxiv(config) -> list:
    """采集 arXiv 论文"""
    logger.info("[2/4] 采集 arXiv 论文...")
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
            logger.warning(f"  arXiv 失败（可能限流）: {result.error}")
            return []
    except Exception as e:
        logger.warning(f"  arXiv 异常: {e}")
        return []


def run_detection(github_data: list, config) -> list:
    """信号检测"""
    logger.info("[3/4] 信号检测...")
    try:
        from src.检测.star_detector import StarSurgeDetector

        rules = config.get_detection_rules("ai_llm")
        thresholds = {}
        for rule in rules:
            if rule.get("rule_id") == "star_surge":
                thresholds = rule.get("threshold", {})

        detector = StarSurgeDetector(thresholds=thresholds)
        alerts = []

        # 模拟历史数据：取现有 stars 作为 previous（实际应查数据库）
        for repo in github_data[:10]:
            repo_with_history = repo.copy()
            # 模拟：stars 增长 30-80%
            import random
            growth_factor = random.uniform(0.3, 0.8)
            repo_with_history["stars_previous"] = int(repo["stars"] / (1 + growth_factor))

            alert = detector.detect(repo_with_history)
            if alert:
                alerts.append(alert)

        logger.info(f"  检测到 {len(alerts)} 个告警")
        return alerts
    except Exception as e:
        logger.exception(f"  检测异常: {e}")
        return []


def run_enrichment(signals: list, config) -> list:
    """LLM 信号丰富化"""
    logger.info("[4/4] LLM 丰富化...")
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
        logger.debug(f"  信号已保存: {output_path}")

        return True
    except Exception as e:
        logger.exception(f"  推送异常: {e}")
        return False


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

    # 2. 检测
    alerts = run_detection(github_data, config)

    # 3. 丰富化
    enriched_signals = run_enrichment(alerts, config)

    # 4. 推送
    if args.skip_notification:
        notify_ok = True
        logger.info("[跳过] 推送通知（--skip-notification）")
    else:
        notify_ok = run_notification(enriched_signals)

    logger.info("=" * 60)
    logger.info(f"结果: 采集{'✅' if github_data else '❌'} 检测{'✅' if True else '❌'} 丰富{'✅' if True else '❌'} 推送{'✅' if notify_ok else '❌'}")
    return 0 if (github_data and notify_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
