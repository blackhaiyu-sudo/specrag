#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求模块API路由（阶段1）
"""

import logging
from flask import Blueprint, request, jsonify
from utils.response import success_response, error_response
from services.requirement_modules.requirement_module_service import RequirementModuleService

logger = logging.getLogger(__name__)

# 创建Blueprint
requirement_modules_bp = Blueprint('requirement_modules', __name__)

# 初始化服务
requirement_module_service = RequirementModuleService()

# ==================== 阶段1 API ====================

@requirement_modules_bp.route('/api/requirement-modules/create', methods=['POST'])
def create_module():
    """创建需求模块"""
    try:
        data = request.json
        
        # 参数验证
        if not data or 'name' not in data or not data.get('name'):
            return error_response('缺少必要参数: name', 400)
        
        name = data.get('name', '').strip()
        if not name:
            return error_response('模块名称不能为空', 400)
        
        # 创建模块（不需要description字段）
        module_id = requirement_module_service.create_module(
            name=name,
            description=None
        )
        
        logger.info(f"创建需求模块成功: {module_id}")
        
        return success_response({
            'module_id': module_id,
            'status': 'draft'
        })
        
    except Exception as e:
        logger.error(f"创建需求模块失败: {str(e)}")
        return error_response(f"创建需求模块失败: {str(e)}", 500)


@requirement_modules_bp.route('/api/requirement-modules/<module_id>/upload-images', methods=['POST'])
def upload_images(module_id):
    """上传图片（支持追加）"""
    try:
        # 检查是否有文件
        if 'images' not in request.files:
            return error_response('未找到上传文件', 400)
        
        files = request.files.getlist('images')
        
        if not files:
            return error_response('未选择文件', 400)
        
        # 上传图片
        result = requirement_module_service.upload_images(module_id, files)
        
        logger.info(f"上传图片: 模块{module_id}, 成功{result['uploaded']}/{len(files)}")
        
        return success_response(result)
        
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"上传图片失败: {str(e)}")
        return error_response(f"上传图片失败: {str(e)}", 500)


@requirement_modules_bp.route('/api/requirement-modules', methods=['GET'])
def list_modules():
    """获取模块列表"""
    try:
        # 获取查询参数
        status = request.args.get('status')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        
        # 参数验证
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 20
        
        # 获取列表
        result = requirement_module_service.list_modules(status, page, limit)
        
        return success_response(result)
        
    except Exception as e:
        logger.error(f"获取模块列表失败: {str(e)}")
        return error_response(f"获取模块列表失败: {str(e)}", 500)


@requirement_modules_bp.route('/api/requirement-modules/<module_id>', methods=['GET'])
def get_module(module_id):
    """获取模块详情"""
    try:
        module = requirement_module_service.get_module(module_id)
        
        if not module:
            return error_response('需求模块不存在', 404)
        
        return success_response(module)
        
    except Exception as e:
        logger.error(f"获取模块详情失败: {str(e)}")
        return error_response(f"获取模块详情失败: {str(e)}", 500)


@requirement_modules_bp.route('/api/requirement-modules/<module_id>', methods=['PUT'])
def update_module(module_id):
    """更新模块信息"""
    try:
        data = request.json
        
        if not data:
            return error_response('请提供要更新的数据', 400)
        
        # 更新模块
        requirement_module_service.update_module(
            module_id=module_id,
            name=data.get('name'),
            description=data.get('description'),
            notes_requirement=data.get('notes_requirement')
        )
        
        logger.info(f"更新模块成功: {module_id}")
        
        return success_response({'message': '更新成功'})
        
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"更新模块失败: {str(e)}")
        return error_response(f"更新模块失败: {str(e)}", 500)


@requirement_modules_bp.route('/api/requirement-modules/<module_id>/images/<image_id>', methods=['DELETE'])
def delete_image(module_id, image_id):
    """删除单张图片"""
    try:
        requirement_module_service.delete_image(module_id, image_id)
        
        logger.info(f"删除图片成功: 模块{module_id}, 图片{image_id}")
        
        return success_response({'message': '删除成功'})
        
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"删除图片失败: {str(e)}")
        return error_response(f"删除图片失败: {str(e)}", 500)


@requirement_modules_bp.route('/api/requirement-modules/<module_id>/reorder-images', methods=['POST'])
def reorder_images(module_id):
    """重新排序图片"""
    try:
        data = request.json
        
        if not data or 'image_ids' not in data:
            return error_response('缺少必要参数: image_ids', 400)
        
        image_ids = data.get('image_ids')
        
        if not isinstance(image_ids, list):
            return error_response('image_ids必须是数组', 400)
        
        requirement_module_service.reorder_images(module_id, image_ids)
        
        logger.info(f"重新排序图片成功: 模块{module_id}")
        
        return success_response({'message': '排序成功'})
        
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"重新排序失败: {str(e)}")
        return error_response(f"重新排序失败: {str(e)}", 500)


@requirement_modules_bp.route('/api/requirement-modules/<module_id>', methods=['DELETE'])
def delete_module(module_id):
    """删除模块（仅草稿状态可删除）"""
    try:
        requirement_module_service.delete_module(module_id)
        
        logger.info(f"删除模块成功: {module_id}")
        
        return success_response({'message': '删除成功'})
        
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"删除模块失败: {str(e)}")
        return error_response(f"删除模块失败: {str(e)}", 500)


# ==================== 注册Blueprint ====================

def register_requirement_module_routes(app):
    """注册路由到Flask应用"""
    app.register_blueprint(requirement_modules_bp)
    logger.info("需求模块路由已注册")
