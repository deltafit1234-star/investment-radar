"""
多租户配置加载器
负责：系统级赛道配置 + 租户追加关键词合并 + sensitivity 阈值映射

核心原则：
- 租户只能追加关键词（append-only），不能覆盖或删除系统关键词
- sensitivity 映射到实际阈值参数
- 按租户加载独立配置，不影响其他租户
"""

from typing import List, Dict, Any, Optional
from loguru import logger

from .database import get_db
from .track_loader import load_track_config, get_track_detection_rules


# Sensitivity → 检测阈值的映射
# high = 低阈值（触发多），medium = 标准，low = 高阈值（触发少）
SENSITIVITY_STAR_SURGE_THRESHOLD = {
    "high": 0.1,    # star增长10%即触发
    "medium": 0.3,
    "low": 0.5,     # star增长50%才触发
}

SENSITIVITY_PAPER_BURST_THRESHOLD = {
    "high": 5,      # 5篇即触发
    "medium": 10,
    "low": 15,
}

SENSITIVITY_PRIORITY_MAP = {
    # sensitivity 决定什么优先级的信号才推送
    "high": "low",    # high敏感度：low/medium/high 都推
    "medium": "medium",
    "low": "high",
}


class TenantConfigLoader:
    """
    按租户加载赛道配置，合并系统关键词 + 租户追加关键词。

    使用方式：
        loader = TenantConfigLoader("tenant_001")
        config = loader.get_track_config("ai_llm")
        keywords = loader.get_merged_keywords("ai_llm")
        threshold = loader.get_threshold("ai_llm", "star_surge")
    """

    def __init__(self, tenant_id: str, db=None):
        self.tenant_id = tenant_id
        self._db = db
        self._subscriptions = None  # 缓存订阅数据
        self._notification_prefs = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_db()
        return self._db

    # ─── 订阅数据 ───────────────────────────────────────────────

    def _load_subscriptions(self):
        """懒加载订阅数据"""
        if self._subscriptions is None:
            subs = self.db.get_tenant_subscriptions(self.tenant_id, enabled_only=True)
            # 转为 {track_id: subscription} 方便快速访问
            self._subscriptions = {sub.track_id: sub for sub in subs}
            logger.debug(f"租户 {self.tenant_id} 加载 {len(self._subscriptions)} 个订阅")
        return self._subscriptions

    def get_subscription(self, track_id: str):
        """获取指定赛道的订阅配置"""
        subs = self._load_subscriptions()
        return subs.get(track_id)

    def is_subscribed(self, track_id: str) -> bool:
        """租户是否订阅了该赛道"""
        return track_id in self._load_subscriptions()

    def get_subscribed_tracks(self) -> List[str]:
        """获取该租户订阅的所有赛道ID"""
        return list(self._load_subscriptions().keys())

    def get_notification_pref(self):
        """获取该租户的推送配置"""
        if self._notification_prefs is None:
            self._notification_prefs = self.db.get_notification_pref(self.tenant_id)
        return self._notification_prefs

    # ─── 关键词合并 ─────────────────────────────────────────────

    def get_merged_keywords(self, track_id: str) -> Dict[str, List[str]]:
        """
        合并系统级赛道关键词 + 租户追加关键词。

        合并规则：
            include = system_include + tenant_append_include
            exclude = system_exclude + tenant_append_exclude

        约束：租户只能追加，不能覆盖或删除系统关键词
        """
        system_config = load_track_config(track_id)
        if not system_config:
            logger.warning(f"赛道配置不存在: {track_id}")
            return {"include": [], "exclude": []}

        system_keywords = system_config.get("keywords", {})
        system_include = system_keywords.get("include", [])
        system_exclude = system_keywords.get("exclude", [])

        sub = self.get_subscription(track_id)
        tenant_include = sub.keywords_append if sub and sub.keywords_append else []
        tenant_exclude = sub.keywords_exclude if sub and sub.keywords_exclude else []

        merged_include = _deduplicate_preserve_order(system_include + tenant_include)
        merged_exclude = _deduplicate_preserve_order(system_exclude + tenant_exclude)

        logger.debug(
            f"关键词合并 [{track_id}] [{self.tenant_id}]: "
            f"系统{len(system_include)}+租户{len(tenant_include)} "
            f"→ 最终{len(merged_include)}个"
        )
        return {"include": merged_include, "exclude": merged_exclude}

    # ─── 阈值映射 ──────────────────────────────────────────────

    def get_sensitivity(self, track_id: str) -> str:
        """获取该租户在该赛道的敏感度"""
        sub = self.get_subscription(track_id)
        return sub.sensitivity if sub else "medium"

    def get_star_surge_threshold(self, track_id: str) -> float:
        """获取 star 激增阈值（0.0-1.0 比例）"""
        sensitivity = self.get_sensitivity(track_id)
        return SENSITIVITY_STAR_SURGE_THRESHOLD.get(sensitivity, 0.3)

    def get_paper_burst_threshold(self, track_id: str) -> int:
        """获取论文激增阈值（篇数）"""
        sensitivity = self.get_sensitivity(track_id)
        return SENSITIVITY_PAPER_BURST_THRESHOLD.get(sensitivity, 10)

    def get_priority_threshold(self, track_id: str) -> str:
        """获取信号优先级阈值（低于此优先级的信号不推送）"""
        sensitivity = self.get_sensitivity(track_id)
        return SENSITIVITY_PRIORITY_MAP.get(sensitivity, "medium")

    # ─── 完整赛道配置（用于 Pipeline） ────────────────────────────

    def get_track_config(self, track_id: str) -> Optional[Dict[str, Any]]:
        """
        获取该租户视角下的完整赛道配置。
        包含合并后的关键词和调整后的阈值。
        """
        if not self.is_subscribed(track_id):
            return None

        system_config = load_track_config(track_id)
        if not system_config:
            return None

        # 深拷贝，避免修改原始配置
        import copy
        config = copy.deepcopy(system_config)

        # 覆盖关键词
        merged = self.get_merged_keywords(track_id)
        config["keywords"] = merged

        # 调整检测规则中的阈值
        sensitivity = self.get_sensitivity(track_id)
        for rule in config.get("detection_rules", []):
            if rule["rule_id"] == "star_surge":
                rule["threshold"]["high"] = SENSITIVITY_STAR_SURGE_THRESHOLD.get(sensitivity, 0.3) * 2
                rule["threshold"]["medium"] = SENSITIVITY_STAR_SURGE_THRESHOLD.get(sensitivity, 0.3)
                rule["threshold"]["low"] = SENSITIVITY_STAR_SURGE_THRESHOLD.get(sensitivity, 0.3) / 2
            elif rule["rule_id"] == "paper_burst":
                rule["threshold"]["high"] = SENSITIVITY_PAPER_BURST_THRESHOLD.get(sensitivity, 10) // 2
                rule["threshold"]["medium"] = SENSITIVITY_PAPER_BURST_THRESHOLD.get(sensitivity, 10)

        # 注入租户信息
        config["_tenant_id"] = self.tenant_id
        config["_sensitivity"] = sensitivity
        config["_priority_threshold"] = self.get_priority_threshold(track_id)

        return config

    # ─── 多租户公共接口（不需要租户订阅判断） ────────────────────

    @staticmethod
    def get_all_subscribed_tenant_ids(track_id: str) -> List[str]:
        """获取订阅了指定赛道的所有租户ID（给 Pipeline 填充 tenant_ids 用）"""
        db = get_db()
        return db.get_tenants_by_track(track_id)

    @staticmethod
    def fill_tenant_ids_for_signal(signal_data: Dict[str, Any], track_id: str) -> Dict[str, Any]:
        """
        信号生成后，填充 tenant_ids。
        策略：所有订阅了该赛道的活跃租户都收到该信号。
        """
        tenant_ids = TenantConfigLoader.get_all_subscribed_tenant_ids(track_id)
        signal_data["tenant_ids"] = tenant_ids
        return signal_data


def _deduplicate_preserve_order(items: List[str]) -> List[str]:
    """去重但保留原始顺序"""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
