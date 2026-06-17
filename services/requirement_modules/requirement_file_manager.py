#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求模块文件管理器
负责图片上传、存储、删除等操作
"""

import os
import shutil
from datetime import datetime
from typing import List, Dict, Optional
from werkzeug.utils import secure_filename
import logging
import uuid

logger = logging.getLogger(__name__)

# PIL为可选依赖，用于获取图片尺寸
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("PIL模块未安装，将无法获取图片尺寸信息")

class RequirementFileManager:
    """需求模块文件管理器"""
    
    def __init__(self, base_dir="outputs/requirement_modules"):
        """
        初始化文件管理器
        
        Args:
            base_dir: 基础存储目录
        """
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
    
    def create_module_directory(self, module_name: str) -> str:
        """
        为需求模块创建目录结构
        
        Args:
            module_name: 模块名称
            
        Returns:
            str: 模块根目录路径
        """
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 安全的模块名称
        safe_name = secure_filename(module_name)
        
        # 创建目录: outputs/requirement_modules/{module_name}/{timestamp}/
        module_dir = os.path.join(self.base_dir, safe_name, timestamp)
        
        # 创建子目录
        images_dir = os.path.join(module_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        logger.info(f"创建需求模块目录: {module_dir}")
        
        return module_dir
    
    def save_uploaded_image(self, module_dir: str, file, order: int = None) -> Dict:
        """
        保存上传的图片
        
        Args:
            module_dir: 模块目录
            file: Flask上传的文件对象
            order: 图片顺序
            
        Returns:
            dict: 图片信息 {"id": "img_xxx", "original_name": "原始文件名.png", "name": "安全文件名", "path": "...", "size": ..., "order": ...}
        """
        # 生成图片ID
        image_id = f"img_{uuid.uuid4().hex[:8]}"
        
        # 保存原始文件名（完整保留，包括中文，包括#备注等所有内容）
        # 注意：第一阶段不解析备注，只是原样保存，第二阶段AI分析时才会解析
        original_filename = file.filename
        
        # 使用UUID生成唯一的安全文件名，保留扩展名
        file_ext = os.path.splitext(original_filename)[1]  # 获取扩展名（如 .png）
        safe_filename = f"{image_id}{file_ext}"  # 使用image_id作为文件名
        
        # 保存路径
        images_dir = os.path.join(module_dir, "images")
        os.makedirs(images_dir, exist_ok=True) # Ensure images directory exists
        file_path = os.path.join(images_dir, safe_filename)
        
        # 保存文件
        file.save(file_path)
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        # 获取图片尺寸（可选，需要PIL支持）
        width, height = None, None
        if HAS_PIL:
            try:
                with Image.open(file_path) as img:
                    width, height = img.size
            except Exception as e:
                logger.debug(f"无法获取图片尺寸: {str(e)}")
        
        logger.info(f"保存图片: 原始名={original_filename}, 安全名={safe_filename}, 大小={file_size} bytes")
        
        # 生成可访问的URL路径
        url_path = '/' + file_path.replace('\\', '/')
        
        return {
            "id": image_id,
            "original_name": original_filename,  # 完整保留原始文件名（包括#备注，用于显示和后续AI分析）
            "name": safe_filename,  # 安全文件名（实际存储的文件名）
            "path": file_path,
            "url": url_path,
            "size": file_size,
            "width": width,
            "height": height,
            "order": order or 1
        }
    
    def delete_image(self, file_path: str) -> bool:
        """
        删除单张图片
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"删除图片: {file_path}")
                return True
            else:
                logger.warning(f"文件不存在: {file_path}")
                return False
        except Exception as e:
            logger.error(f"删除图片失败: {str(e)}")
            return False
    
    def delete_module_directory(self, module_dir: str) -> bool:
        """
        删除整个模块目录
        
        Args:
            module_dir: 模块目录路径
            
        Returns:
            bool: 是否成功
        """
        try:
            if os.path.exists(module_dir):
                shutil.rmtree(module_dir)
                logger.info(f"删除模块目录: {module_dir}")
                return True
            else:
                logger.warning(f"目录不存在: {module_dir}")
                return False
        except Exception as e:
            logger.error(f"删除模块目录失败: {str(e)}")
            return False
    
    def validate_image_file(self, file) -> tuple:
        """
        验证上传的图片文件
        
        Args:
            file: 上传的文件对象
            
        Returns:
            tuple: (是否有效, 错误信息)
        """
        # 检查文件是否存在
        if not file or file.filename == '':
            return False, "未选择文件"
        
        # 检查文件扩展名
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if ext not in allowed_extensions:
            return False, f"不支持的文件格式: {ext}，请上传 {', '.join(allowed_extensions)}"
        
        # 检查文件大小（5MB限制）
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        
        # Flask文件对象大小检查
        file.seek(0, 2)  # 移动到文件末尾
        file_size = file.tell()
        file.seek(0)  # 重置到开头
        
        if file_size > MAX_FILE_SIZE:
            return False, f"文件过大: {file_size/1024/1024:.2f}MB，最大允许5MB"
        
        if file_size == 0:
            return False, "文件为空"
        
        return True, None
    
    def generate_notes_file(self, module_dir: str, notes_requirement: str = None) -> Optional[str]:
        """
        生成notes.txt文件（供阶段2使用）
        
        Args:
            module_dir: 模块目录
            notes_requirement: 需求文档补充
            
        Returns:
            str: notes.txt文件路径，如果没有备注则返回None
        """
        # 检查是否有任何备注
        if not notes_requirement:
            logger.info("没有备注内容，不生成notes.txt")
            return None
        
        # 生成notes.txt内容
        content = ""
        
        if notes_requirement:
            content += "#%需求文档补充%#\n"
            content += notes_requirement.strip() + "\n\n"
        
        # 保存文件
        notes_file_path = os.path.join(module_dir, "notes.txt")
        
        with open(notes_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"生成notes.txt文件: {notes_file_path}")
        
        return notes_file_path
