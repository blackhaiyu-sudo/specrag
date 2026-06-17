"""
PRD业务逻辑服务
"""
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional
import logging

from database.models import PRD, DatabaseManager

logger = logging.getLogger(__name__)

class PRDService:
    """PRD管理服务"""
    
    def __init__(self, db_manager: DatabaseManager, upload_folder: str = "uploads"):
        self.db_manager = db_manager
        self.upload_folder = upload_folder
        os.makedirs(self.upload_folder, exist_ok=True)
        logger.info("PRDService initialized.")
    
    def create_prd(self, name: str, content: str) -> str:
        """
        创建PRD
        
        Args:
            name: PRD名称
            content: PRD内容（Markdown格式）
        
        Returns:
            prd_id: PRD的ID
        """
        session = self.db_manager.get_session()
        
        try:
            # 生成ID
            prd_id = str(uuid.uuid4())
            
            # 保存到文件
            file_path = os.path.join(self.upload_folder, f"{prd_id}.md")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 创建数据库记录
            prd = PRD(
                id=prd_id,
                name=name,
                content=content,
                file_path=file_path,
                status='draft',
                mode='普通模式',  # 默认值
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(prd)
            session.commit()
            
            logger.info(f"创建PRD成功: {name} (ID: {prd_id})")
            return prd_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"创建PRD失败: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_prd(self, prd_id: str) -> Optional[Dict]:
        """
        获取PRD详情
        
        Args:
            prd_id: PRD的ID
        
        Returns:
            PRD的字典表示，如果不存在则返回None
        """
        session = self.db_manager.get_session()
        
        try:
            prd = session.query(PRD).filter_by(id=prd_id).first()
            
            if not prd:
                return None
            
            prd_dict = prd.to_dict()
            
            return prd_dict
            
        finally:
            session.close()
    
    def list_prds(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict:
        """
        获取PRD列表
        
        Args:
            status: 过滤状态（draft/processing/completed）
            limit: 每页数量
            offset: 偏移量
        
        Returns:
            {'prds': [...], 'total': int}
        """
        session = self.db_manager.get_session()
        
        try:
            query = session.query(PRD)
            
            # 状态过滤
            if status:
                query = query.filter_by(status=status)
            
            # 排序：最新的在前
            query = query.order_by(PRD.created_at.desc())
            
            # 总数
            total = query.count()
            
            # 分页
            prds = query.limit(limit).offset(offset).all()
            
            # 转换为前端展示字典
            prd_list = []
            for prd in prds:
                prd_dict = prd.to_dict()
                
                prd_list.append(prd_dict)
            
            return {
                'prds': prd_list,
                'total': total
            }
            
        finally:
            session.close()
    
    def update_prd(self, prd_id: str, **kwargs) -> bool:
        """
        更新PRD
        
        Args:
            prd_id: PRD的ID
            **kwargs: 要更新的字段（content, mode, business, description等）
        
        Returns:
            是否成功
        """
        session = self.db_manager.get_session()
        
        try:
            prd = session.query(PRD).filter_by(id=prd_id).first()
            
            if not prd:
                logger.warning(f"PRD不存在: {prd_id}")
                return False
            
            # 如果修改内容且PRD不是草稿状态，记录警告
            if 'content' in kwargs and prd.status != 'draft':
                logger.warning(f"⚠️ 正在编辑非草稿状态的PRD内容: {prd_id} (状态: {prd.status})")
            
            # 更新字段
            allowed_fields = ['content', 'name', 'mode', 'business', 'description', 'status']
            updated = False
            
            for field, value in kwargs.items():
                if field in allowed_fields and value is not None:
                    setattr(prd, field, value)
                    updated = True
            
            if updated:
                prd.updated_at = datetime.utcnow()
                
                # 如果content更新了，同步更新文件
                if 'content' in kwargs and prd.file_path:
                    try:
                        with open(prd.file_path, 'w', encoding='utf-8') as f:
                            f.write(kwargs['content'])
                        logger.info(f"PRD内容文件已同步更新: {prd.file_path}")
                    except Exception as e:
                        logger.error(f"同步PRD文件失败: {str(e)}")
                        # 不抛出异常，允许数据库更新继续
                
                session.commit()
                logger.info(f"更新PRD成功: {prd_id} (更新字段: {list(kwargs.keys())})")
                return True
            
            return False
            
        except Exception as e:
            session.rollback()
            logger.error(f"更新PRD失败: {str(e)}")
            raise
        finally:
            session.close()
    
    def delete_prd(self, prd_id: str) -> bool:
        """
        删除PRD
        
        Args:
            prd_id: PRD的ID
        
        Returns:
            是否成功
        """
        session = self.db_manager.get_session()
        
        try:
            prd = session.query(PRD).filter_by(id=prd_id).first()
            
            if not prd:
                logger.warning(f"PRD不存在: {prd_id}")
                return False
            
            # 删除文件
            if prd.file_path and os.path.exists(prd.file_path):
                os.remove(prd.file_path)
            
            # 删除数据库记录
            session.delete(prd)
            session.commit()
            
            logger.info(f"删除PRD成功: {prd_id}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"删除PRD失败: {str(e)}")
            raise
        finally:
            session.close()
