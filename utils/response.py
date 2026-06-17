"""
响应格式化工具
提供统一的API响应格式

标准响应格式：
成功: { "success": true, "code": 0, "data": {...}, "message": "..." }
失败: { "success": false, "code": -1, "error": "错误信息" }

前端统一判断方式：
- 成功判断: response.data.code === 0 或 response.data.success
- 获取数据: response.data.data.xxx
- 获取错误: response.data.error
"""

def success_response(data=None, message=None, code=200):
    """标准成功响应格式
    
    Args:
        data: 响应数据（会包装在 data 字段中）
        message: 可选的成功消息
        code: HTTP状态码（默认200）
    
    Returns:
        tuple: (响应字典, HTTP状态码)
    """
    response = {
        'success': True,
        'code': 0
    }
    
    if data is not None:
        response['data'] = data
        
    if message is not None:
        response['message'] = message
        
    return response, code

def error_response(message, code=400):
    """标准错误响应格式
    
    Args:
        message: 错误信息
        code: HTTP状态码（默认400）
    
    Returns:
        tuple: (响应字典, HTTP状态码)
    """
    return {
        'success': False,
        'code': -1,
        'error': message
    }, code 