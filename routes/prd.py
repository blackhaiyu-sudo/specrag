"""
PRD相关路由（重构版）
"""
import os
import logging
from datetime import datetime
from flask import Blueprint, request, send_file
from utils.response import success_response, error_response

logger = logging.getLogger(__name__)
prd_bp = Blueprint('prd', __name__)

def register_prd_routes(app, prd_service, generation_service):
    """注册PRD相关路由"""
    
    # ========== PRD管理API ==========
    
    @app.route('/api/prds/upload', methods=['POST'], endpoint='upload_text_prd')
    def upload_text_prd():
        """
        上传PRD文档
        请求体：{"name": "...", "content": "..."}
        返回：{"success": true, "prd_id": "..."}
        """
        try:
            data = request.json
            if not data or 'content' not in data:
                return error_response('缺少必要参数: content', 400)
            
            content = data.get('content')
            name = data.get('name', f"PRD_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
            
            # 创建PRD（草稿状态）
            prd_id = prd_service.create_prd(name, content)
            
            logger.info(f"上传PRD成功: {name} (ID: {prd_id})")
            
            return success_response({
                'prd_id': prd_id,
                'name': name,
                'status': 'draft'
            })
            
        except Exception as e:
            logger.error(f"上传PRD失败: {str(e)}")
            return error_response(f"上传PRD失败: {str(e)}", 500)
    
    @app.route('/api/prds', methods=['GET'])
    def list_prds():
        """
        获取PRD列表
        查询参数：status, limit, offset
        返回：{"success": true, "prds": [...], "total": int}
        """
        try:
            status = request.args.get('status')
            limit = int(request.args.get('limit', 50))
            offset = int(request.args.get('offset', 0))
            
            result = prd_service.list_prds(status=status, limit=limit, offset=offset)
            
            return success_response(result)
            
        except Exception as e:
            logger.error(f"获取PRD列表失败: {str(e)}")
            return error_response(f"获取PRD列表失败: {str(e)}", 500)
    
    @app.route('/api/prds/<prd_id>', methods=['GET'])
    def get_prd(prd_id):
        """
        获取PRD详情
        返回：{"success": true, "prd": {...}}
        """
        try:
            prd = prd_service.get_prd(prd_id)
            
            if not prd:
                return error_response('PRD不存在', 404)
            
            return success_response({'prd': prd})
            
        except Exception as e:
            logger.error(f"获取PRD详情失败: {str(e)}")
            return error_response(f"获取PRD详情失败: {str(e)}", 500)
    
    @app.route('/api/prds/<prd_id>', methods=['PUT'])
    def update_prd(prd_id):
        """
        更新PRD（内容、配置等）
        请求体：{"content": "...", "mode": "...", "business": "...", "description": "..."}
        返回：{"success": true, "message": "更新成功"}
        """
        try:
            data = request.json
            
            if not data:
                return error_response('缺少请求数据', 400)
            
            # 更新PRD
            success = prd_service.update_prd(prd_id, **data)
            
            if not success:
                return error_response('PRD不存在或更新失败', 404)
            
            logger.info(f"更新PRD成功: {prd_id}")
            
            return success_response({'message': '更新成功'})
            
        except Exception as e:
            logger.error(f"更新PRD失败: {str(e)}")
            return error_response(f"更新PRD失败: {str(e)}", 500)
    
    @app.route('/api/prds/<prd_id>', methods=['DELETE'])
    def delete_prd(prd_id):
        """
        删除PRD
        返回：{"success": true, "message": "删除成功"}
        """
        try:
            success = prd_service.delete_prd(prd_id)
            
            if not success:
                return error_response('PRD不存在或删除失败', 404)
            
            logger.info(f"删除PRD成功: {prd_id}")
            
            return success_response({'message': '删除成功'})
            
        except Exception as e:
            logger.error(f"删除PRD失败: {str(e)}")
            return error_response(f"删除PRD失败: {str(e)}", 500)
    
    @app.route('/api/prds/<prd_id>/download', methods=['GET'])
    def download_prd(prd_id):
        """
        下载PRD文档
        返回：Markdown文件
        """
        try:
            prd = prd_service.get_prd(prd_id)
            
            if not prd:
                return error_response('PRD不存在', 404)
            
            # 确保文件存在
            file_path = prd.get('file_path')
            if not file_path or not os.path.exists(file_path):
                return error_response('PRD文件不存在', 404)
            
            return send_file(
                file_path,
                mimetype='text/markdown',
                as_attachment=True,
                download_name=f"{prd['name']}.md"
            )
            
        except Exception as e:
            logger.error(f"下载PRD失败: {str(e)}")
            return error_response(f"下载PRD失败: {str(e)}", 500)
    
    # 注册Blueprint
    app.register_blueprint(prd_bp, url_prefix='/api/prd')
    
    return app
