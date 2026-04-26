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
    tenant_ids = Column(JSON)                           # 需要通知的租户ID列表
    is_read = Column(Boolean, default=False)           # 是否已读
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "track_id": self.track_id,
            "source_id": self.source_id,
            "signal_type": self.signal_type,
            "title": self.title,
            "content": self.content,
            "priority": self.priority,
            "keywords": self.keywords,
            "meaning": self.meaning,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
