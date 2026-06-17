"""
知识库导入与召回测试服务
"""

import os
import logging
from flask import Flask, render_template
from dotenv import load_dotenv

from config import Config
from database.models import DatabaseManager
from routes.prd import register_prd_routes
from routes.kb import register_kb_routes
from routes.requirement_modules import register_requirement_module_routes
from services.prd.prd_service import PRDService
from utils.response import success_response, error_response

load_dotenv()

LOG_DIR = os.environ.get('LOG_DIR', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
APP_LOG_FILE = os.environ.get('APP_LOG_FILE', os.path.join(LOG_DIR, 'app.log'))

# 创建日志记录器
logging.basicConfig(
    level=getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(APP_LOG_FILE)
    ]
)

logger = logging.getLogger(__name__)


def create_app(config_obj=None):
    """创建 KB-only Flask 应用"""

    # 创建应用实例
    app = Flask(__name__, static_folder='static', static_url_path='/static')

    # 使用配置对象
    if config_obj is None:
        config_obj = Config()
    app.config.from_object(config_obj)

    # 确保必要的目录结构存在
    ensure_directories_exist(app)

    db_manager = DatabaseManager()
    db_manager.initialize()
    prd_service = PRDService(
        db_manager=db_manager,
        upload_folder=app.config.get('UPLOAD_FOLDER', 'uploads')
    )

    # 保留原文本 PRD 和图片需求的创建/上传/编辑交互。
    # generation_service 传 None，前端启动动作已改为调用 KB 导入接口。
    register_prd_routes(app, prd_service, generation_service=None)
    register_requirement_module_routes(app)

    # 注册知识库路由。
    register_kb_routes(app)
    logger.info("知识库路由注册完成")

    # 添加静态文件路由
    @app.route('/')
    def index():
        return render_template('kb_workspace.html')

    @app.route('/improved')
    def vue_client_improved():
        return render_template('kb_workspace.html')

    @app.route('/api/status')
    def status():
        return success_response({'status': 'running', 'service': 'kb'})

    # 提供outputs目录的静态文件访问（用于图片等）
    @app.route('/outputs/<path:filename>')
    def serve_outputs(filename):
        """提供outputs目录下的文件访问（已加固：防止路径遍历攻击）"""
        from flask import send_from_directory, abort
        from utils.security import get_safe_path, is_safe_path

        # 定义允许访问的基础目录
        outputs_dir = os.path.abspath('outputs')

        # 安全检查：验证请求的路径在 outputs 目录内
        if not is_safe_path(outputs_dir, filename):
            logger.warning(f"路径遍历攻击尝试被阻止: {repr(filename)}")
            abort(403)  # 禁止访问

        # 获取安全路径
        safe_path = get_safe_path(outputs_dir, filename)
        if safe_path is None:
            logger.warning(f"无效的文件路径请求: {repr(filename)}")
            abort(400)  # 错误请求

        # 检查文件是否存在
        if not os.path.isfile(safe_path):
            abort(404)  # 文件不存在

        # 使用 send_from_directory 安全地发送文件
        return send_from_directory(outputs_dir, filename)

    # 全局错误处理
    @app.errorhandler(404)
    def page_not_found(e):
        return error_response('资源不存在', 404)

    @app.errorhandler(500)
    def internal_server_error(e):
        return error_response('服务器内部错误', 500)

    return app


def ensure_directories_exist(app):
    """确保所有必要的目录结构存在"""
    directories = [
        app.config['UPLOAD_FOLDER'],  # 上传文件夹
        'data',
        'runtime',
        'runtime/kb_cleaning',
        'runtime/kb_query_hints',
        'outputs/html',
        'outputs/raw',
        'logs',                       # 日志文件夹
        'static/libs'                 # 本地库文件夹
    ]

    for directory in directories:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"创建目录: {directory}")
            except Exception as e:
                logger.error(f"创建目录失败 {directory}: {e}")


app = create_app()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5002, debug=True)
