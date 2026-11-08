import os
import json
import logging

logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        """初始化默认配置"""
        self.DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
        self.UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
        self.MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
        self.ALLOWED_EXTENSIONS = {'md', 'txt', 'pdf', 'docx'}

        # OpenAI API配置
        self.CONFIG_LIST = self.load_config() or []

    def load_config(self):
        """加载 OpenAI-compatible API 配置。"""
        # 检查环境变量是否包含配置路径
        config_path = os.environ.get('AUTOGEN_CONFIG_PATH')
        
        # 如果环境变量中没有设置，则尝试从标准路径加载
        if not config_path or not os.path.exists(config_path):
            # 先尝试配置目录
            config_path = os.path.join('config', 'OAI_CONFIG_LIST')
            if not os.path.exists(config_path):
                # 再尝试项目根目录
                config_path = 'OAI_CONFIG_LIST'
        
        # 尝试加载配置
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding="utf-8") as f:
                    config_list = json.load(f)
                
                logger.info(f"成功加载配置文件: {config_path}")
                return config_list
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                return None
        else:
            logger.warning(f"配置文件不存在: {config_path}")
            return None
    
