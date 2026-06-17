"""Database models for PRD import and knowledge-base staging data."""

from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class PRD(Base):
    """PRD文档模型"""
    __tablename__ = 'prds'
    
    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    file_path = Column(String(512))
    status = Column(String(20), default='draft')  # draft/processing/completed
    mode = Column(String(20), default='知识库导入')  # 保留给旧数据/前端显示
    business = Column(String(100))  # 业务类型
    description = Column(Text)  # 描述说明
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 索引优化
    __table_args__ = (
        Index('idx_prd_created_at', 'created_at'),
        Index('idx_prd_name', 'name'),
        Index('idx_prd_status', 'status'),
    )
    
    def to_dict(self):
        """序列化为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'content': self.content,
            'file_path': self.file_path,
            'status': self.status,
            'mode': self.mode,
            'business': self.business,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class RequirementModule(Base):
    """需求模块表 - 图片需求收集"""
    __tablename__ = 'requirement_modules'
    
    # ========== 基本信息 ==========
    id = Column(String(100), primary_key=True, comment='需求模块ID: req_mod_xxx')
    name = Column(String(255), nullable=False, comment='需求大模块名称，如：产品v1.2.3_功能名称')
    description = Column(Text, comment='模块描述')
    
    # ========== 状态管理 ==========
    status = Column(String(50), default='draft', comment='状态: draft/processing/completed/failed')
    # draft: 草稿（可编辑）
    # processing: 导入中
    # completed: 已完成
    # failed: 导入失败
    
    # ========== 图片信息 ==========
    image_count = Column(Integer, default=0, comment='图片数量')
    image_directory = Column(String(512), comment='图片存储目录')
    images = Column(JSON, comment='图片列表: [{"id": "img_001", "name": "...", "path": "...", "size": 1024, "order": 1}]')
    notes = Column(JSON, comment='图片备注信息: {"filename": {"module": "模块名", "change_type": "新增"}}')
    
    # ========== 备注信息 ==========
    notes_requirement = Column(Text, nullable=True, comment='需求文档补充：背景、功能点等')
    
    # ========== 知识库导入流程相关 ==========
    processing_stage = Column(String(50), comment='当前处理阶段: analyzing_images/generating_prd/importing_kb/completed')
    progress = Column(Integer, default=0, comment='进度百分比 0-100')
    
    # ========== 分析结果存储 ==========
    module_analyses = Column(Text, comment='各模块图片分析结果(JSON): {"module_name": {"analysis": "...", "evaluation": "..."}}')
    
    # ========== PRD 相关 ==========
    prd_version_content = Column(Text, comment='版本PRD内容（阶段2生成）')
    prd_final_content = Column(Text, comment='知识库源PRD内容')
    prd_file_path = Column(String(500), comment='PRD文件路径')
    
    # ========== 错误信息 ==========
    error_message = Column(Text, comment='错误信息')
    error_stage = Column(String(50), comment='出错阶段')
    
    # ========== 时间戳 ==========
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    completed_at = Column(DateTime, comment='完成时间')
    
    # 索引
    __table_args__ = (
        Index('idx_req_mod_status_created', 'status', 'created_at'),
        Index('idx_req_mod_name', 'name'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'image_count': self.image_count,
            'image_directory': self.image_directory,
            'images': self.images or [],
            'notes_requirement': self.notes_requirement,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

# 数据库连接管理
class DatabaseManager:
    """数据库管理器 - 单例模式"""
    _instance = None
    _engine = None
    _session_factory = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, database_url=None):
        """初始化数据库连接"""
        if self._engine is None:
            import os
            os.makedirs("data", exist_ok=True)
            database_url = database_url or os.environ.get("DATABASE_URL") or "sqlite:///data/specrag_app.db"

            self._engine = create_engine(
                database_url,
                echo=False,
                pool_pre_ping=True,
                connect_args={"check_same_thread": False}
            )

            Base.metadata.create_all(self._engine)
            self._session_factory = sessionmaker(bind=self._engine)

    def get_session(self):
        """获取数据库会话"""
        if self._session_factory is None:
            raise RuntimeError("数据库未初始化，请先调用initialize()")
        return self._session_factory()

    def get_engine(self):
        """获取数据库引擎"""
        return self._engine


# 全局数据库管理器实例
db_manager = DatabaseManager()
