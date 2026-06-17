#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求模块业务逻辑服务（阶段1）
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from database.models import RequirementModule, DatabaseManager
from services.requirement_modules.requirement_file_manager import RequirementFileManager

logger = logging.getLogger(__name__)

class RequirementModuleService:
    """需求模块服务（阶段1：需求收集）"""
    
    def __init__(self, logging_service=None):
        """初始化服务"""
        self.db_manager = DatabaseManager()
        self.db_manager.initialize()
        self.file_manager = RequirementFileManager()
        self.logging_service = logging_service
    
    def create_module(self, name: str, description: str = None) -> str:
        """
        创建需求模块
        
        Args:
            name: 模块名称
            description: 模块描述
            
        Returns:
            str: 模块ID
        """
        session = self.db_manager.get_session()
        
        try:
            # 生成模块ID
            module_id = f"req_mod_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 创建模块目录
            module_dir = self.file_manager.create_module_directory(name)
            
            # 创建数据库记录
            module = RequirementModule(
                id=module_id,
                name=name,
                description=description,
                status='draft',
                image_directory=module_dir,
                image_count=0,
                images=[]
            )
            
            session.add(module)
            session.commit()
            
            logger.info(f"创建需求模块: {module_id}, 名称: {name}")
            
            return module_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"创建需求模块失败: {str(e)}")
            raise
        finally:
            session.close()
    
    def upload_images(self, module_id: str, files: List) -> Dict:
        """
        上传图片到模块（支持追加）
        
        Args:
            module_id: 模块ID
            files: 文件列表
            
        Returns:
            dict: {"uploaded": 3, "total_images": 5, "failed": [], "images": [...]}
        """
        session = self.db_manager.get_session()
        
        try:
            # 获取模块
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            if not module:
                raise ValueError(f"需求模块不存在: {module_id}")
            
            # 允许导入记录重复运行，用户可能需要补充或替换图片后重新生成。
            
            # 获取现有图片列表
            images = module.images or []
            current_max_order = max([img.get('order', 0) for img in images]) if images else 0
            
            uploaded = 0
            failed = []
            new_images = []
            
            for file in files:
                try:
                    # 验证文件
                    valid, error_msg = self.file_manager.validate_image_file(file)
                    if not valid:
                        failed.append({"filename": file.filename, "error": error_msg})
                        continue
                    
                    # 保存文件
                    image_info = self.file_manager.save_uploaded_image(
                        module.image_directory, 
                        file,
                        order=current_max_order + uploaded + 1
                    )
                    images.append(image_info)
                    new_images.append(image_info)
                    uploaded += 1
                    
                except Exception as e:
                    logger.error(f"上传文件失败 {file.filename}: {str(e)}")
                    failed.append({"filename": file.filename, "error": str(e)})
            
            # 更新数据库
            module.images = images
            module.image_count = len(images)
            module.updated_at = datetime.utcnow()
            
            # 标记JSON字段已修改（SQLAlchemy需要）
            flag_modified(module, 'images')
            
            session.commit()
            
            logger.info(f"模块 {module_id} 上传图片: 成功{uploaded}, 失败{len(failed)}, 总计{len(images)}")
            
            return {
                "uploaded": uploaded,
                "total_images": len(images),
                "failed": failed,
                "images": new_images
            }
            
        except Exception as e:
            session.rollback()
            logger.error(f"上传图片失败: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_module(self, module_id: str) -> Optional[Dict]:
        """
        获取模块详情
        
        Args:
            module_id: 模块ID
            
        Returns:
            dict: 模块信息
        """
        session = self.db_manager.get_session()
        
        try:
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            
            if not module:
                return None
            
            module_dict = module.to_dict()
            
            # 为旧数据的图片补充缺失的url和original_name字段
            if module_dict.get('images'):
                updated_images = []
                for img in module_dict['images']:
                    # 如果缺少url字段，根据path生成
                    if 'url' not in img and 'path' in img:
                        path = img['path'].replace('\\', '/')
                        img['url'] = '/' + path if not path.startswith('/') else path
                    
                    # 如果缺少original_name，使用name作为降级
                    if 'original_name' not in img and 'name' in img:
                        img['original_name'] = img['name']
                    
                    updated_images.append(img)
                
                module_dict['images'] = updated_images
            
            return module_dict
            
        finally:
            session.close()
    
    def list_modules(self, status: str = None, page: int = 1, limit: int = 20) -> Dict:
        """
        获取模块列表
        
        Args:
            status: 状态筛选
            page: 页码（从1开始）
            limit: 每页数量
            
        Returns:
            dict: {"modules": [...], "total": 100, "page": 1, "limit": 20}
        """
        session = self.db_manager.get_session()
        
        try:
            # 构建查询
            query = session.query(RequirementModule)
            
            if status:
                query = query.filter_by(status=status)
            
            # 总数
            total = query.count()
            
            # 分页
            offset = (page - 1) * limit
            modules = query.order_by(RequirementModule.created_at.desc()) \
                          .offset(offset) \
                          .limit(limit) \
                          .all()
            
            return {
                "modules": [module.to_dict() for module in modules],
                "total": total,
                "page": page,
                "limit": limit
            }
            
        finally:
            session.close()
    
    def update_module(self, module_id: str, name: str = None, description: str = None,
                     notes_requirement: str = None) -> bool:
        """
        更新模块信息
        
        Args:
            module_id: 模块ID
            name: 新名称
            description: 描述
            notes_requirement: 需求文档补充
            
        Returns:
            bool: 是否成功
        """
        session = self.db_manager.get_session()
        
        try:
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            
            if not module:
                raise ValueError(f"需求模块不存在: {module_id}")
            
            # 用户可能需要在导入完成后补充或修改备注、名称等信息。
            
            # 更新字段
            if name is not None:
                module.name = name
            if description is not None:
                module.description = description
            if notes_requirement is not None:
                module.notes_requirement = notes_requirement
            
            module.updated_at = datetime.utcnow()
            
            session.commit()
            
            logger.info(f"更新需求模块: {module_id} (状态: {module.status})")
            
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"更新模块失败: {str(e)}")
            raise
        finally:
            session.close()
    
    def delete_image(self, module_id: str, image_id: str) -> bool:
        """
        删除模块中的单张图片
        
        Args:
            module_id: 模块ID
            image_id: 图片ID
            
        Returns:
            bool: 是否成功
        """
        session = self.db_manager.get_session()
        
        try:
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            
            if not module:
                raise ValueError(f"需求模块不存在: {module_id}")
            
            # 允许导入记录重复运行，用户可能需要删除错误或多余的图片后重新生成。
            
            # 查找图片
            images = module.images or []
            image_to_delete = None
            
            for img in images:
                if img['id'] == image_id:
                    image_to_delete = img
                    break
            
            if not image_to_delete:
                raise ValueError(f"图片不存在: {image_id}")
            
            # 删除物理文件
            self.file_manager.delete_image(image_to_delete['path'])
            
            # 从列表中移除
            images.remove(image_to_delete)
            module.images = images
            module.image_count = len(images)
            module.updated_at = datetime.utcnow()
            
            # 标记JSON字段已修改（SQLAlchemy需要）
            flag_modified(module, 'images')
            
            session.commit()
            
            logger.info(f"删除图片: 模块{module_id}, 图片{image_id}")
            
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"删除图片失败: {str(e)}")
            raise
        finally:
            session.close()
    
    def reorder_images(self, module_id: str, image_ids: List[str]) -> bool:
        """
        重新排序图片
        
        Args:
            module_id: 模块ID
            image_ids: 图片ID列表（按新顺序）
            
        Returns:
            bool: 是否成功
        """
        session = self.db_manager.get_session()
        
        try:
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            
            if not module:
                raise ValueError(f"需求模块不存在: {module_id}")
            
            # 允许导入记录重复运行，用户可能需要调整图片顺序后重新生成。
            
            images = module.images or []
            
            # 创建ID到图片的映射
            image_map = {img['id']: img for img in images}
            
            # 按新顺序重建列表
            new_images = []
            for order, img_id in enumerate(image_ids, start=1):
                if img_id in image_map:
                    img = image_map[img_id]
                    img['order'] = order
                    new_images.append(img)
            
            module.images = new_images
            module.updated_at = datetime.utcnow()
            
            session.commit()
            
            logger.info(f"重新排序图片: 模块{module_id}")
            
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"重新排序失败: {str(e)}")
            raise
        finally:
            session.close()
    
    def delete_module(self, module_id: str) -> bool:
        """
        删除模块及其所有文件（允许所有状态删除）
        
        Args:
            module_id: 模块ID
            
        Returns:
            bool: 是否成功
        """
        session = self.db_manager.get_session()
        
        try:
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            
            if not module:
                raise ValueError(f"需求模块不存在: {module_id}")
            
            # 用户可能需要删除错误的或不需要的导入记录，无论其状态如何。
            
            # 删除文件目录
            if module.image_directory:
                self.file_manager.delete_module_directory(module.image_directory)
            
            # 删除数据库记录
            session.delete(module)
            session.commit()
            
            logger.info(f"删除需求模块: {module_id}")
            
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"删除模块失败: {str(e)}")
            raise
        finally:
            session.close()
