"""
自定义异常类
提供应用中使用的各种异常定义
"""

class AppError(Exception):
    """应用自定义异常基类"""
    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ResourceNotFoundError(AppError):
    """资源不存在异常"""
    def __init__(self, resource_type, resource_id):
        message = f"{resource_type} {resource_id} 不存在"
        super().__init__(message, 404)


class ValidationError(AppError):
    """数据验证异常"""
    def __init__(self, message):
        super().__init__(message, 400)


class ServiceError(AppError):
    """服务层异常"""
    def __init__(self, message):
        super().__init__(message, 500) 