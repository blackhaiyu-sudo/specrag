#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全工具模块
提供路径安全验证、文件ID验证等安全相关功能
"""

import os
import logging
from werkzeug.security import safe_join

logger = logging.getLogger(__name__)

# ==================== 路径安全 ====================

def is_safe_path(base_dir: str, requested_path: str) -> bool:
    """
    检查请求的路径是否在允许的基础目录内
    防止路径遍历攻击（如 ../../etc/passwd）

    Args:
        base_dir: 允许访问的基础目录
        requested_path: 请求的路径（可能包含恶意的 ../ 等）

    Returns:
        bool: 路径是否安全
    """
    try:
        # 🔒 预检查：拒绝包含危险模式的路径
        dangerous_patterns = ['..', '\x00']
        for pattern in dangerous_patterns:
            if pattern in requested_path:
                logger.warning(f"路径包含危险模式 '{pattern}': {repr(requested_path)}")
                return False

        # 🔒 检查反斜杠（Windows路径分隔符）- 在所有平台上都拒绝
        if '\\' in requested_path:
            logger.warning(f"路径包含反斜杠: {repr(requested_path)}")
            return False

        # 获取基础目录的绝对路径
        base_abs = os.path.abspath(base_dir)

        # 使用 safe_join 安全拼接路径（Werkzeug 提供）
        # 如果路径不安全，safe_join 返回 None
        safe_path = safe_join(base_dir, requested_path)

        if safe_path is None:
            logger.warning(f"路径安全检查失败（safe_join返回None）: base={base_dir}, requested={requested_path}")
            return False

        # 获取最终路径的绝对路径
        final_abs = os.path.abspath(safe_path)

        # 确保最终路径在基础目录内
        # 使用 os.path.commonpath 或简单的前缀检查
        if not final_abs.startswith(base_abs + os.sep) and final_abs != base_abs:
            logger.warning(f"路径安全检查失败（路径逃逸）: base={base_abs}, final={final_abs}")
            return False

        return True

    except Exception as e:
        logger.error(f"路径安全检查异常: {str(e)}")
        return False


def get_safe_path(base_dir: str, requested_path: str) -> str:
    """
    获取安全的文件路径，如果路径不安全则返回 None

    Args:
        base_dir: 允许访问的基础目录
        requested_path: 请求的路径

    Returns:
        str: 安全的绝对路径，如果不安全则返回 None
    """
    try:
        # 使用 Werkzeug 的 safe_join
        safe_path = safe_join(base_dir, requested_path)

        if safe_path is None:
            logger.warning(f"获取安全路径失败: base={base_dir}, requested={requested_path}")
            return None

        # 获取绝对路径
        abs_path = os.path.abspath(safe_path)
        base_abs = os.path.abspath(base_dir)

        # 再次验证路径在基础目录内
        if not abs_path.startswith(base_abs + os.sep) and abs_path != base_abs:
            logger.warning(f"路径逃逸检测: {abs_path} 不在 {base_abs} 内")
            return None

        return abs_path

    except Exception as e:
        logger.error(f"获取安全路径异常: {str(e)}")
        return None

