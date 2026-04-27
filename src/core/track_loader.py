"""
赛道配置加载器
从 config/tracks/ 目录加载所有赛道配置
"""

import os
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

TRACKS_DIR = Path(__file__).parent.parent.parent / "config" / "tracks"


def load_track_config(track_id: str) -> Optional[Dict[str, Any]]:
    """加载单个赛道配置"""
    track_file = TRACKS_DIR / f"{track_id}.yaml"
    if not track_file.exists():
        logger.warning(f"赛道配置文件不存在: {track_file}")
        return None
    with open(track_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_enabled_tracks() -> List[Dict[str, Any]]:
    """获取所有已启用的赛道"""
    if not TRACKS_DIR.exists():
        logger.error(f"赛道配置目录不存在: {TRACKS_DIR}")
        return []

    tracks = []
    for track_file in sorted(TRACKS_DIR.glob("*.yaml")):
        track_id = track_file.stem
        if track_id.startswith("."):
            continue
        config = load_track_config(track_id)
        if config and config.get("enabled", False):
            tracks.append(config)
        elif config:
            logger.debug(f"赛道已禁用: {track_id}")
        else:
            logger.warning(f"赛道加载失败: {track_id}")

    logger.info(f"已启用赛道: {[t['track_id'] for t in tracks]}")
    return tracks


def get_track_ids() -> List[str]:
    """获取所有赛道ID"""
    if not TRACKS_DIR.exists():
        return []
    return [f.stem for f in sorted(TRACKS_DIR.glob("*.yaml")) if not f.stem.startswith(".")]


def get_all_tracks() -> List[Dict[str, Any]]:
    """获取所有赛道（含禁用的）"""
    if not TRACKS_DIR.exists():
        return []
    tracks = []
    for track_file in sorted(TRACKS_DIR.glob("*.yaml")):
        track_id = track_file.stem
        if track_id.startswith("."):
            continue
        config = load_track_config(track_id)
        if config:
            tracks.append(config)
    return tracks


# ─── 快速访问函数 ────────────────────────────────────────────

def get_track_name(track_id: str) -> str:
    """获取赛道名称"""
    config = load_track_config(track_id)
    return config["track_name"] if config else track_id


def get_track_keywords(track_id: str) -> Dict[str, List[str]]:
    """获取赛道关键词"""
    config = load_track_config(track_id)
    if not config:
        return {"include": [], "exclude": []}
    return config.get("keywords", {"include": [], "exclude": []})


def get_track_sources(track_id: str) -> List[Dict[str, Any]]:
    """获取赛道数据源"""
    config = load_track_config(track_id)
    return config.get("sources", []) if config else []


def get_track_detection_rules(track_id: str) -> List[Dict[str, Any]]:
    """获取赛道检测规则"""
    config = load_track_config(track_id)
    return config.get("detection_rules", []) if config else []
