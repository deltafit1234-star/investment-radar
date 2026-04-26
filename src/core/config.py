"""
配置加载模块
负责加载全局配置和赛道配置
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from loguru import logger


class Config:
    """配置管理类"""
    
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            # 默认从项目根目录加载
            self.config_dir = Path(__file__).parent.parent.parent / "config"
        else:
            self.config_dir = Path(config_dir)
        
        self._settings: Dict = {}
        self._tracks: Dict[str, Dict] = {}
        self._load_settings()
    
    def _load_settings(self):
        """加载全局设置"""
        settings_path = self.config_dir / "settings.yaml"
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                self._settings = yaml.safe_load(f) or {}
            logger.info(f"全局配置加载成功: {settings_path}")
        else:
            logger.warning(f"配置文件不存在: {settings_path}")
    
    def _load_track(self, track_id: str) -> Optional[Dict]:
        """加载单个赛道配置"""
        track_path = self.config_dir / "tracks" / f"{track_id}.yaml"
        if track_path.exists():
            with open(track_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return None
    
    def get_settings(self) -> Dict:
        """获取全局设置"""
        return self._settings
    
    def get_track(self, track_id: str) -> Optional[Dict]:
        """获取赛道配置（带缓存）"""
        if track_id not in self._tracks:
            self._tracks[track_id] = self._load_track(track_id)
        return self._tracks[track_id]
    
    def get_all_tracks(self) -> List[str]:
        """获取所有已配置的赛道ID"""
        tracks_dir = self.config_dir / "tracks"
        if not tracks_dir.exists():
            return []
        return [f.stem for f in tracks_dir.glob("*.yaml")]
    
    def get_source_config(self, track_id: str, source_id: str) -> Optional[Dict]:
        """获取特定赛道的特定数据源配置"""
        track = self.get_track(track_id)
        if not track:
            return None
        sources = track.get("sources", [])
        for source in sources:
            if source.get("source_id") == source_id:
                return source
        return None
    
    def get_detection_rules(self, track_id: str) -> List[Dict]:
        """获取赛道的检测规则"""
        track = self.get_track(track_id)
        if not track:
            return []
        return track.get("detection_rules", [])
    
    @property
    def db_path(self) -> str:
        """获取数据库路径"""
        db_config = self._settings.get("database", {})
        return db_config.get("path", "data/radar.db")
    
    @property
    def llm_config(self) -> Dict:
        """获取LLM配置"""
        return self._settings.get("llm", {})
    
    @property
    def debug_mode(self) -> bool:
        """是否调试模式"""
        return self._settings.get("app", {}).get("debug", False)


# 全局配置实例
_config: Optional[Config] = None


def get_config(config_dir: Optional[str] = None) -> Config:
    """获取全局配置实例（单例）"""
    global _config
    if _config is None:
        _config = Config(config_dir)
    return _config


def reload_config():
    """重新加载配置"""
    global _config
    _config = None
    _config = get_config()
