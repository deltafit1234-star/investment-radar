"""
数据库模块
负责数据存储和访问
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from .config import get_config

Base = declarative_base()


class Signal(Base):
    """信号表"""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(String(50), index=True)           # 赛道ID
    source_id = Column(String(50))                      # 数据源ID
    signal_type = Column(String(50))                    # 信号类型
    title = Column(String(500))                         # 标题
    content = Column(Text)                              # 内容/摘要
    raw_data = Column(JSON)                             # 原始数据
    priority = Column(String(20), default="low")       # high/medium/low
    keywords = Column(JSON)                             # 匹配的关键词
    meaning = Column(Text)                              # 含义解读
    tenant_ids = Column(JSON)                           # 需要通知的租户ID列表（所有订阅该赛道的租户）
    is_read = Column(Boolean, default=False)           # 是否已读
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Premium 深度分析（高级服务）
    analysis_premium = Column(JSON, nullable=True)     # Premium租户深度分析
    ad_space = Column(Text, nullable=True)              # 初级租户广告位文案
    has_premium_content = Column(Boolean, default=False)

    def to_dict(self, tenant_plan: str = "basic") -> Dict[str, Any]:
        result = {
            "id": self.id,
            "track_id": self.track_id,
            "source_id": self.source_id,
            "signal_type": self.signal_type,
            "title": self.title,
            "content": self.content,
            "priority": self.priority,
            "keywords": self.keywords,
            "meaning": self.meaning,
            "tenant_ids": self.tenant_ids,
            "is_read": self.is_read,
            "has_premium_content": self.has_premium_content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if tenant_plan == "premium" and self.analysis_premium:
            result["analysis_premium"] = self.analysis_premium
        elif self.has_premium_content:
            result["ad_space"] = self.ad_space or "🔒 升级高级版解锁深度分析"
        return result


class Tenant(Base):
    """租户表"""
    __tablename__ = "tenants"

    id = Column(String(50), primary_key=True)           # tenant_001
    name = Column(String(200), nullable=False)           # "XX科技基金"
    plan = Column(String(20), default="basic")          # basic / premium
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "plan": self.plan,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TenantSubscription(Base):
    """租户赛道订阅表"""
    __tablename__ = "tenant_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    track_id = Column(String(50), nullable=False)
    sensitivity = Column(String(20), default="medium")  # high / medium / low
    keywords_append = Column(JSON, nullable=True)       # 租户追加关键词（append-only）
    keywords_exclude = Column(JSON, nullable=True)      # 租户排除关键词
    plan = Column(String(20), default="basic")          # basic / premium（订阅粒度）
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_tenant_track', 'tenant_id', 'track_id', unique=True),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "track_id": self.track_id,
            "sensitivity": self.sensitivity,
            "keywords_append": self.keywords_append or [],
            "keywords_exclude": self.keywords_exclude or [],
            "plan": self.plan,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TenantNotificationPref(Base):
    """租户推送配置表"""
    __tablename__ = "tenant_notification_prefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False, unique=True, index=True)
    wechat_target = Column(String(200), nullable=True)  # 微信群 chat_id 或 webhook
    feishu_webhook = Column(String(500), nullable=True)  # 飞书 webhook（预留）
    email = Column(String(200), nullable=True)           # 邮件地址（预留）
    daily_brief_time = Column(String(10), default="08:30")
    real_time_alert_enabled = Column(Boolean, default=True)
    real_time_threshold = Column(String(20), default="medium")  # 触发即时推送的最低优先级
    weekly_report_enabled = Column(Boolean, default=False)
    weekly_report_day = Column(String(10), default="monday")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "wechat_target": self.wechat_target,
            "feishu_webhook": self.feishu_webhook,
            "email": self.email,
            "daily_brief_time": self.daily_brief_time,
            "real_time_alert_enabled": self.real_time_alert_enabled,
            "real_time_threshold": self.real_time_threshold,
            "weekly_report_enabled": self.weekly_report_enabled,
            "weekly_report_day": self.weekly_report_day,
        }


class Alert(Base):
    """告警表"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, index=True)             # 关联信号ID
    tenant_id = Column(String(50), index=True)          # 租户ID
    channel = Column(String(20))                        # 推送渠道 wechat/feishu/email
    status = Column(String(20), default="pending")      # pending/sent/failed
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "signal_id": self.signal_id,
            "tenant_id": self.tenant_id,
            "channel": self.channel,
            "status": self.status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DailyReport(Base):
    """每日情报报告表（Phase 2 - Premium专属）"""
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(String(50), nullable=False, index=True)
    track_name = Column(String(200))
    report_date = Column(String(10), nullable=False)       # YYYY-MM-DD
    is_silent = Column(Boolean, default=False)             # 静默日标记
    signal_count = Column(Integer, default=0)
    high_priority_count = Column(Integer, default=0)
    merged_count = Column(Integer, default=0)               # 合并过来的信号数
    themes = Column(JSON, nullable=True)                   # 主题分组
    report_text = Column(Text, nullable=True)              # 推送用文本
    report_data = Column(JSON, nullable=True)              # 完整数据（存库）
    generated_at = Column(DateTime, default=datetime.utcnow)
    pushed_at = Column(DateTime, nullable=True)             # 推送时间
    status = Column(String(20), default="pending")          # pending/pushed/failed

    __table_args__ = (
        Index('idx_daily_report_track_date', 'track_id', 'report_date', unique=True),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "track_id": self.track_id,
            "track_name": self.track_name,
            "report_date": self.report_date,
            "is_silent": self.is_silent,
            "signal_count": self.signal_count,
            "high_priority_count": self.high_priority_count,
            "merged_count": self.merged_count,
            "themes": self.themes,
            "report_text": self.report_text,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
            "status": self.status,
        }


class ReportSignal(Base):
    """报告-信号关联表（报告包含哪些信号）"""
    __tablename__ = "report_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, nullable=False, index=True)   # 关联 DailyReport.id
    signal_id = Column(Integer, nullable=True)                # 关联 Signal.id（可能为空，信号已过期）
    signal_title = Column(String(500))                        # 信号标题（冗余存储，防信号过期）
    signal_type = Column(String(50))
    priority = Column(String(20))
    source = Column(String(50))                               # 数据来源（itjuzi/github/arxiv等）
    added_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_report_signal_report', 'report_id'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "signal_id": self.signal_id,
            "signal_title": self.signal_title,
            "signal_type": self.signal_type,
            "priority": self.priority,
            "source": self.source,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


class TrendingArchive(Base):
    """GitHub Trending 每日归档表"""
    __tablename__ = "trending_archive"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner = Column(String(100))
    repo = Column(String(100))
    stars = Column(Integer)
    rank = Column(Integer)          # 当天排名
    daily_stars_gained = Column(Integer, nullable=True)  # 当天增长（估算）
    description = Column(Text, nullable=True)
    language = Column(String(50), nullable=True)
    archive_date = Column(String(10))  # YYYY-MM-DD 格式
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_trending_archive_date', 'archive_date'),
        Index('idx_trending_archive_repo_date', 'owner', 'repo', 'archive_date'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner": self.owner,
            "repo": self.repo,
            "stars": self.stars,
            "rank": self.rank,
            "daily_stars_gained": self.daily_stars_gained,
            "description": self.description,
            "language": self.language,
            "archive_date": self.archive_date,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class StarHistory(Base):
    """GitHub 项目 Star 历史表"""
    __tablename__ = "star_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner = Column(String(100))        # 仓库所有者
    repo = Column(String(100))         # 仓库名
    stars = Column(Integer)            # 当前 star 数
    rank = Column(Integer, nullable=True)  # 当天 trending 排名
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_star_history_repo_fetched', 'owner', 'repo', 'fetched_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner": self.owner,
            "repo": self.repo,
            "stars": self.stars,
            "rank": self.rank,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class RawData(Base):
    """原始数据缓存表"""
    __tablename__ = "raw_data"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(50), index=True)          # 数据源ID
    data_type = Column(String(50))                      # 数据类型
    external_id = Column(String(255))                   # 外部数据ID（如GitHub repo name）
    data = Column(JSON)                                 # 原始数据
    fetched_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "data_type": self.data_type,
            "external_id": self.external_id,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class Database:
    """数据库管理类"""
    
    _instance: Optional["Database"] = None
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            config = get_config()
            db_path = config.db_path
        
        # 确保目录存在
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 🚨 SHORTcut: 使用 SQLite 进行本地验证
        # TODO(FUTURE): 生产环境改为 PostgreSQL
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,  # 🔧 DEBUG: SQL查询调试时可改为 True
            pool_pre_ping=True
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info(f"数据库初始化成功: {db_path}")
    
    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> "Database":
        """获取数据库单例"""
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance
    
    def init_tables(self):
        """初始化表结构"""
        Base.metadata.create_all(self.engine)
        logger.info("数据库表初始化完成")
    
    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    def add_signal(self, signal_data: Dict[str, Any]) -> Signal:
        """添加信号"""
        session = self.get_session()
        try:
            signal = Signal(**signal_data)
            session.add(signal)
            session.commit()
            session.refresh(signal)
            logger.info(f"信号已添加: {signal.id} - {signal.title[:50]}")
            return signal
        except Exception as e:
            session.rollback()
            logger.error(f"添加信号失败: {e}")
            raise
        finally:
            session.close()
    
    def get_signals(
        self,
        track_id: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Signal]:
        """获取信号列表"""
        session = self.get_session()
        try:
            query = session.query(Signal)
            if track_id:
                query = query.filter(Signal.track_id == track_id)
            if priority:
                query = query.filter(Signal.priority == priority)
            query = query.order_by(Signal.created_at.desc())
            return query.limit(limit).offset(offset).all()
        finally:
            session.close()
    
    def get_signal_by_id(self, signal_id: int) -> Optional[Signal]:
        """根据ID获取信号"""
        session = self.get_session()
        try:
            return session.query(Signal).filter(Signal.id == signal_id).first()
        finally:
            session.close()
    
    def update_signal(self, signal_id: int, updates: Dict[str, Any]) -> Optional[Signal]:
        """更新信号"""
        session = self.get_session()
        try:
            signal = session.query(Signal).filter(Signal.id == signal_id).first()
            if signal:
                for key, value in updates.items():
                    setattr(signal, key, value)
                session.commit()
                session.refresh(signal)
            return signal
        finally:
            session.close()
    
    def save_raw_data(self, source_id: str, data_type: str, external_id: str, data: Dict) -> RawData:
        """保存原始数据"""
        session = self.get_session()
        try:
            raw = RawData(
                source_id=source_id,
                data_type=data_type,
                external_id=external_id,
                data=data
            )
            session.add(raw)
            session.commit()
            session.refresh(raw)
            return raw
        except Exception as e:
            session.rollback()
            logger.error(f"保存原始数据失败: {e}")
            raise
        finally:
            session.close()
    
    def get_latest_raw_data(self, source_id: str, external_id: str) -> Optional[RawData]:
        """获取最新的原始数据"""
        session = self.get_session()
        try:
            return (
                session.query(RawData)
                .filter(
                    RawData.source_id == source_id,
                    RawData.external_id == external_id
                )
                .order_by(RawData.fetched_at.desc())
                .first()
            )
        finally:
            session.close()

    # ─── Star History ──────────────────────────────────────────────
    def save_star_snapshot(self, owner: str, repo: str, stars: int, rank: int = None) -> StarHistory:
        """保存一次 star 快照"""
        session = self.get_session()
        try:
            snap = StarHistory(owner=owner, repo=repo, stars=stars, rank=rank)
            session.add(snap)
            session.commit()
            session.refresh(snap)
            return snap
        except Exception as e:
            session.rollback()
            logger.error(f"保存 star 快照失败: {e}")
            raise
        finally:
            session.close()

    def save_trending_archive(self, repos: List[Dict[str, Any]], archive_date: str = None) -> int:
        """
        批量保存每日 Trending 归档

        Args:
            repos: GitHub Trending 仓库列表（按排名排序）
            archive_date: 归档日期，默认今天

        Returns:
            保存的记录数
        """
        if not archive_date:
            archive_date = datetime.utcnow().strftime("%Y-%m-%d")

        session = self.get_session()
        saved = 0
        try:
            for i, repo in enumerate(repos):
                full_name = repo.get("full_name", "")
                if "/" not in full_name:
                    continue
                owner, repo_name = full_name.split("/", 1)

                # 获取昨天的快照估算日增长
                prev = self._get_stars_at_date(session, owner, repo_name, archive_date)
                daily_gained = None
                if prev is not None:
                    daily_gained = repo.get("stars", 0) - prev

                record = TrendingArchive(
                    owner=owner,
                    repo=repo_name,
                    stars=repo.get("stars", 0),
                    rank=i + 1,
                    daily_stars_gained=daily_gained,
                    description=repo.get("description", ""),
                    language=repo.get("language", ""),
                    archive_date=archive_date,
                )
                session.add(record)
                saved += 1

            session.commit()
            logger.info(f"Trending 归档已保存: {archive_date} - {saved} 条")
            return saved
        except Exception as e:
            session.rollback()
            logger.error(f"保存 Trending 归档失败: {e}")
            raise
        finally:
            session.close()

    def _get_stars_at_date(self, session: Session, owner: str, repo: str, before_date: str) -> Optional[int]:
        """查询指定日期之前的最近一次 star 数"""
        from datetime import datetime as dt
        try:
            date_cutoff = dt.strptime(before_date, "%Y-%m-%d")
            record = (
                session.query(StarHistory)
                .filter(
                    StarHistory.owner == owner,
                    StarHistory.repo == repo,
                    StarHistory.fetched_at < date_cutoff
                )
                .order_by(StarHistory.fetched_at.desc())
                .first()
            )
            return record.stars if record else None
        except Exception:
            return None

    def get_trending_archive(
        self,
        archive_date: str,
        limit: int = 100
    ) -> List[TrendingArchive]:
        """获取指定日期的 Trending 归档"""
        session = self.get_session()
        try:
            return (
                session.query(TrendingArchive)
                .filter(TrendingArchive.archive_date == archive_date)
                .order_by(TrendingArchive.rank.asc())
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def get_repo_trend_days(self, owner: str, repo: str, days: int = 30) -> int:
        """查询某项目出现在 Trending 的天数（近 N 天）"""
        from datetime import timedelta
        session = self.get_session()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            count = (
                session.query(TrendingArchive)
                .filter(
                    TrendingArchive.owner == owner,
                    TrendingArchive.repo == repo,
                    TrendingArchive.archive_date >= cutoff
                )
                .count()
            )
            return count
        finally:
            session.close()

    def get_previous_stars(self, owner: str, repo: str, hours: int = 24) -> Optional[StarHistory]:
        """获取最近一次 star 快照"""
        from datetime import timedelta
        session = self.get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            return (
                session.query(StarHistory)
                .filter(
                    StarHistory.owner == owner,
                    StarHistory.repo == repo,
                    StarHistory.fetched_at < cutoff
                )
                .order_by(StarHistory.fetched_at.desc())
                .first()
            )
        finally:
            session.close()

    def get_star_trend(self, owner: str, repo: str, days: int = 7) -> List[Dict[str, Any]]:
        """获取 star 趋势（最近 N 天）"""
        from datetime import timedelta
        session = self.get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            records = (
                session.query(StarHistory)
                .filter(
                    StarHistory.owner == owner,
                    StarHistory.repo == repo,
                    StarHistory.fetched_at >= cutoff
                )
                .order_by(StarHistory.fetched_at.asc())
                .all()
            )
            return [r.to_dict() for r in records]
        finally:
            session.close()

    # ─── 信号去重 ──────────────────────────────────────────────
    def is_duplicate_signal(
        self,
        track_id: str,
        signal_type: str,
        title: str,
        days: int = 7,
        similarity_threshold: float = 0.8,
    ) -> Optional[Signal]:
        """
        检查是否存在重复信号。
        条件：同赛道 + 同类型 + 标题相似度 > threshold
        返回已存在的信号，或 None（不重复）
        """
        if not title:
            return None

        from datetime import timedelta
        import re

        session = self.get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            candidates = (
                session.query(Signal)
                .filter(
                    Signal.track_id == track_id,
                    Signal.signal_type == signal_type,
                    Signal.created_at >= cutoff,
                )
                .all()
            )

            title_norm = self._normalize_text(title)
            for sig in candidates:
                if not sig.title:
                    continue
                sim = self._text_similarity(title_norm, self._normalize_text(sig.title))
                if sim >= similarity_threshold:
                    return sig
            return None
        finally:
            session.close()

    @staticmethod
    def _normalize_text(text: str) -> str:
        """标准化文本：小写+去除标点"""
        import re
        text = text.lower().strip()
        text = re.sub(r"[^\w\u4e00-\u9fff]", "", text)  # 保留字母数字中文
        text = re.sub(r"\s+", "", text)
        return text

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """简单编辑距离相似度"""
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        # Jaccard: 字符集合交集/并集
        set_a, set_b = set(a), set(b)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def get_signals_after(self, signal_id: int, track_id: str = None, limit: int = 100) -> List[Signal]:
        """获取指定ID之后的信号（用于SSE增量推送）"""
        session = self.get_session()
        try:
            query = session.query(Signal).filter(Signal.id > signal_id)
            if track_id:
                query = query.filter(Signal.track_id == track_id)
            return query.order_by(Signal.id.asc()).limit(limit).all()
        finally:
            session.close()

    def get_latest_signal_id(self, track_id: str = None) -> int:
        """获取最新信号的ID（用于SSE初始last_id）"""
        session = self.get_session()
        try:
            query = session.query(Signal)
            if track_id:
                query = query.filter(Signal.track_id == track_id)
            latest = query.order_by(Signal.id.desc()).first()
            return latest.id if latest else 0
        finally:
            session.close()

    def get_recent_duplicates(
        self,
        track_id: str,
        signal_type: str,
        title: str,
        days: int = 7,
    ) -> List[Signal]:
        """获取所有相似信号（用于展示/调试）"""
        dup = self.is_duplicate_signal(track_id, signal_type, title, days)
        return [dup] if dup else []


    # ─── 多租户：Tenant ─────────────────────────────────────────
    def upsert_tenant(self, tenant_id: str, name: str, plan: str = "basic") -> Tenant:
        """创建或更新租户"""
        session = self.get_session()
        try:
            tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                tenant.name = name
                tenant.plan = plan
            else:
                tenant = Tenant(id=tenant_id, name=name, plan=plan)
                session.add(tenant)
            session.commit()
            session.refresh(tenant)
            return tenant
        finally:
            session.close()

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        session = self.get_session()
        try:
            return session.query(Tenant).filter(Tenant.id == tenant_id).first()
        finally:
            session.close()

    def get_all_active_tenants(self) -> List[Tenant]:
        session = self.get_session()
        try:
            return session.query(Tenant).filter(Tenant.is_active == True).all()
        finally:
            session.close()

    # ─── 多租户：TenantSubscription ─────────────────────────────
    def upsert_subscription(
        self,
        tenant_id: str,
        track_id: str,
        sensitivity: str = "medium",
        keywords_append: List[str] = None,
        keywords_exclude: List[str] = None,
        plan: str = "basic",
        enabled: bool = True,
    ) -> TenantSubscription:
        """创建或更新租户订阅"""
        session = self.get_session()
        try:
            sub = (
                session.query(TenantSubscription)
                .filter(TenantSubscription.tenant_id == tenant_id, TenantSubscription.track_id == track_id)
                .first()
            )
            if sub:
                sub.sensitivity = sensitivity
                sub.keywords_append = keywords_append
                sub.keywords_exclude = keywords_exclude
                sub.plan = plan
                sub.enabled = enabled
            else:
                sub = TenantSubscription(
                    tenant_id=tenant_id,
                    track_id=track_id,
                    sensitivity=sensitivity,
                    keywords_append=keywords_append,
                    keywords_exclude=keywords_exclude,
                    plan=plan,
                    enabled=enabled,
                )
                session.add(sub)
            session.commit()
            session.refresh(sub)
            return sub
        finally:
            session.close()

    def get_subscription(self, tenant_id: str, track_id: str) -> Optional[TenantSubscription]:
        session = self.get_session()
        try:
            return (
                session.query(TenantSubscription)
                .filter(TenantSubscription.tenant_id == tenant_id, TenantSubscription.track_id == track_id)
                .first()
            )
        finally:
            session.close()

    def get_tenant_subscriptions(self, tenant_id: str, enabled_only: bool = True) -> List[TenantSubscription]:
        session = self.get_session()
        try:
            query = session.query(TenantSubscription).filter(TenantSubscription.tenant_id == tenant_id)
            if enabled_only:
                query = query.filter(TenantSubscription.enabled == True)
            return query.all()
        finally:
            session.close()

    def get_tenants_by_track(self, track_id: str) -> List[str]:
        """获取订阅了指定赛道的所有租户ID"""
        session = self.get_session()
        try:
            subs = (
                session.query(TenantSubscription)
                .filter(TenantSubscription.track_id == track_id, TenantSubscription.enabled == True)
                .all()
            )
            return list(set(sub.tenant_id for sub in subs))
        finally:
            session.close()

    def delete_subscription(self, tenant_id: str, track_id: str) -> bool:
        session = self.get_session()
        try:
            sub = (
                session.query(TenantSubscription)
                .filter(TenantSubscription.tenant_id == tenant_id, TenantSubscription.track_id == track_id)
                .first()
            )
            if sub:
                session.delete(sub)
                session.commit()
                return True
            return False
        finally:
            session.close()

    # ─── 多租户：TenantNotificationPref ─────────────────────────
    def upsert_notification_pref(
        self,
        tenant_id: str,
        wechat_target: str = None,
        feishu_webhook: str = None,
        email: str = None,
        daily_brief_time: str = "08:30",
        real_time_alert_enabled: bool = True,
        real_time_threshold: str = "medium",
        weekly_report_enabled: bool = False,
        weekly_report_day: str = "monday",
    ) -> TenantNotificationPref:
        """创建或更新租户推送配置"""
        session = self.get_session()
        try:
            pref = session.query(TenantNotificationPref).filter(TenantNotificationPref.tenant_id == tenant_id).first()
            if pref:
                pref.wechat_target = wechat_target or pref.wechat_target
                pref.feishu_webhook = feishu_webhook or pref.feishu_webhook
                pref.email = email or pref.email
                pref.daily_brief_time = daily_brief_time
                pref.real_time_alert_enabled = real_time_alert_enabled
                pref.real_time_threshold = real_time_threshold
                pref.weekly_report_enabled = weekly_report_enabled
                pref.weekly_report_day = weekly_report_day
            else:
                pref = TenantNotificationPref(
                    tenant_id=tenant_id,
                    wechat_target=wechat_target,
                    feishu_webhook=feishu_webhook,
                    email=email,
                    daily_brief_time=daily_brief_time,
                    real_time_alert_enabled=real_time_alert_enabled,
                    real_time_threshold=real_time_threshold,
                    weekly_report_enabled=weekly_report_enabled,
                    weekly_report_day=weekly_report_day,
                )
                session.add(pref)
            session.commit()
            session.refresh(pref)
            return pref
        finally:
            session.close()

    def get_notification_pref(self, tenant_id: str) -> Optional[TenantNotificationPref]:
        session = self.get_session()
        try:
            return session.query(TenantNotificationPref).filter(TenantNotificationPref.tenant_id == tenant_id).first()
        finally:
            session.close()

    # ─── 多租户：按租户获取信号 ─────────────────────────────────
    def get_signals_for_tenant(
        self,
        tenant_id: str,
        track_id: str = None,
        priority: str = None,
        limit: int = 100,
        offset: int = 0,
        tenant_plan: str = "basic",
    ) -> List[Dict[str, Any]]:
        """获取属于指定租户的信号（Signal.tenant_ids 包含该租户ID）"""
        session = self.get_session()
        try:
            query = session.query(Signal)
            if track_id:
                query = query.filter(Signal.track_id == track_id)
            if priority:
                query = query.filter(Signal.priority == priority)
            query = query.order_by(Signal.created_at.desc())
            signals = query.limit(limit).offset(offset).all()
            # 过滤出包含该 tenant_id 的信号
            result = []
            for sig in signals:
                if sig.tenant_ids and tenant_id in sig.tenant_ids:
                    result.append(sig.to_dict(tenant_plan=tenant_plan))
            return result
        finally:
            session.close()

    # ─── DailyReport（Phase 2）─────────────────────────────────────────
    def save_daily_report(self, report_data: Dict[str, Any]) -> DailyReport:
        """保存每日报告"""
        session = self.get_session()
        try:
            report = DailyReport(
                track_id=report_data["track_id"],
                track_name=report_data.get("track_name", ""),
                report_date=report_data["report_date"],
                is_silent=report_data.get("is_silent", False),
                signal_count=report_data.get("signal_count", 0),
                high_priority_count=report_data.get("high_priority_count", 0),
                merged_count=report_data.get("merged_count", 0),
                themes=report_data.get("themes"),
                report_text=report_data.get("report_text"),
                report_data=report_data.get("report_data"),
                status="pending",
            )
            session.add(report)
            session.commit()
            session.refresh(report)
            logger.info(f"日报已保存: {report.track_id} - {report.report_date}")
            return report
        except Exception as e:
            session.rollback()
            # 已存在则更新
            if "UNIQUE" in str(e) or "duplicate" in str(e).lower():
                return self._update_daily_report(session, report_data)
            logger.error(f"保存日报失败: {e}")
            raise
        finally:
            session.close()

    def _update_daily_report(self, session: Session, report_data: Dict[str, Any]) -> DailyReport:
        """更新已存在的日报"""
        try:
            report = (
                session.query(DailyReport)
                .filter(
                    DailyReport.track_id == report_data["track_id"],
                    DailyReport.report_date == report_data["report_date"],
                )
                .first()
            )
            if report:
                report.signal_count = report_data.get("signal_count", report.signal_count)
                report.high_priority_count = report_data.get("high_priority_count", report.high_priority_count)
                report.merged_count = report_data.get("merged_count", report.merged_count)
                report.themes = report_data.get("themes", report.themes)
                report.report_text = report_data.get("report_text", report.report_text)
                report.report_data = report_data.get("report_data", report.report_data)
                report.status = "pending"
                session.commit()
                session.refresh(report)
            return report
        except Exception as e:
            session.rollback()
            raise

    def save_report_signal(self, report_id: int, signal: Dict[str, Any]) -> ReportSignal:
        """保存报告-信号关联"""
        session = self.get_session()
        try:
            rs = ReportSignal(
                report_id=report_id,
                signal_id=signal.get("id"),
                signal_title=(signal.get("full_name") or signal.get("title", ""))[:500],
                signal_type=signal.get("type", ""),
                priority=signal.get("priority", "low"),
                source=signal.get("type", ""),
            )
            session.add(rs)
            session.commit()
            session.refresh(rs)
            return rs
        except Exception as e:
            session.rollback()
            logger.warning(f"保存报告信号关联失败: {e}")
            raise
        finally:
            session.close()

    def get_daily_reports(
        self,
        track_id: Optional[str] = None,
        report_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[DailyReport]:
        """获取日报列表"""
        session = self.get_session()
        try:
            query = session.query(DailyReport)
            if track_id:
                query = query.filter(DailyReport.track_id == track_id)
            if report_date:
                query = query.filter(DailyReport.report_date == report_date)
            return query.order_by(DailyReport.report_date.desc()).limit(limit).all()
        finally:
            session.close()

    def get_pending_daily_reports(self) -> List[DailyReport]:
        """获取待推送的日报"""
        session = self.get_session()
        try:
            return (
                session.query(DailyReport)
                .filter(DailyReport.status == "pending")
                .order_by(DailyReport.generated_at.asc())
                .all()
            )
        finally:
            session.close()

    def mark_report_pushed(self, report_id: int) -> None:
        """标记日报已推送"""
        session = self.get_session()
        try:
            report = session.query(DailyReport).filter(DailyReport.id == report_id).first()
            if report:
                from datetime import datetime as dt
                report.status = "pushed"
                report.pushed_at = dt.utcnow()
                session.commit()
        finally:
            session.close()

    def is_duplicate_report(self, track_id: str, report_date: str) -> bool:
        """检查某赛道某日期是否已有报告"""
        session = self.get_session()
        try:
            existing = (
                session.query(DailyReport)
                .filter(
                    DailyReport.track_id == track_id,
                    DailyReport.report_date == report_date,
                )
                .first()
            )
            return existing is not None
        finally:
            session.close()


# 全局数据库实例
_db: Optional[Database] = None


def get_db() -> Database:
    """获取全局数据库实例"""
    global _db
    if _db is None:
        _db = Database.get_instance()
    return _db


def init_db():
    """初始化数据库"""
    db = get_db()
    db.init_tables()
    return db
