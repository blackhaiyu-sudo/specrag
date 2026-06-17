"""
模型选择工具模块
提供统一的模型筛选逻辑
"""

import logging

logger = logging.getLogger(__name__)


def get_models_by_type(config_list, model_type=None):
    """
    根据模型类型筛选配置列表
    
    Args:
        config_list: LLM配置列表
        model_type: 模型类型
            - None 或 "text": 返回普通文本模型（默认，排除 vision/split 模型）
            - "split": 返回需求拆分/PRD Knowledge 模型
            - "vision": 返回Vision模型（用于图片分析）
    
    Returns:
        list: 筛选后的配置列表（已清理内部字段）
    
    Examples:
        >>> # 获取文本模型（默认）
        >>> text_models = get_models_by_type(config_list)
        >>> text_models = get_models_by_type(config_list, "text")
        
        >>> # 获取Vision模型
        >>> vision_models = get_models_by_type(config_list, "vision")
    """
    if not config_list:
        logger.warning("配置列表为空")
        return []
    
    # 默认返回文本模型
    if model_type is None or model_type == "text":
        filtered_configs = _get_text_models(config_list)
    elif model_type == "split":
        filtered_configs = _get_split_models(config_list)
    elif model_type == "vision":
        filtered_configs = _get_vision_models(config_list)
    else:
        logger.warning(f"未知的模型类型: {model_type}，返回所有配置")
        filtered_configs = config_list
    
    # 清理内部字段（model_type 不应该传递给 LLM API）
    return _clean_internal_fields(filtered_configs)


def _get_vision_models(config_list):
    """
    获取Vision模型配置
    
    优先级：
    1. 查找 model_type == "vision" 的配置（推荐）
    2. 关键词匹配（向后兼容旧配置）
    3. 回退到第一个可用配置（可能不支持图片）
    """
    vision_config = []
    
    # 方法1：优先使用 model_type 字段
    for cfg in config_list:
        if not _is_enabled(cfg):
            continue
        if cfg.get('model_type') == 'vision':
            vision_config.append(cfg)
    
    if vision_config:
        logger.info(f"✅ 使用Vision模型（基于model_type）: {vision_config[0].get('model')}")
        return vision_config
    
    # 方法2：如果没有 model_type 字段，回退到关键词匹配（向后兼容）
    logger.info("📝 配置中未找到model_type字段，使用关键词匹配模式")
    
    # 优先顺序：doubao-vision > qwen-vl > 其他vision模型
    for priority_keyword in [['doubao', 'vision'], ['qwen-vl'], ['vision', 'vl']]:
        for cfg in config_list:
            if not _is_enabled(cfg):
                continue
            model_name = cfg.get('model', '').lower()
            if all(keyword in model_name for keyword in priority_keyword):
                vision_config.append(cfg)
                logger.info(f"✅ 使用Vision模型（基于关键词）: {cfg.get('model')}")
                return vision_config
    
    # 方法3：如果还是找不到，使用第一个可用配置（警告）
    logger.warning("⚠️  未找到Vision模型配置，将使用第一个可用配置（可能不支持图片分析）")
    return [cfg for cfg in config_list if _is_enabled(cfg)]


def _get_text_models(config_list):
    """
    获取文本模型配置（排除Vision模型）
    
    优先级：
    1. 查找 model_type != "vision" 或未设置 model_type 的配置（推荐）
    2. 关键词匹配排除vision模型（向后兼容旧配置）
    3. 返回所有配置
    """
    text_config = []
    
    # 方法1：优先使用 model_type 字段
    # 原则：默认是text模型，只有特殊模型（如vision）才需要标注
    for cfg in config_list:
        if not _is_enabled(cfg):
            continue
        model_type = cfg.get('model_type')
        # 如果没有 model_type 字段，视为默认的 text 模型
        # split/vision 是专用模型，不进入普通文本 agent
        if model_type is None or model_type == 'text':
            text_config.append(cfg)
    
    if text_config:
        logger.info(f"✅ 使用文本模型: {text_config[0].get('model')}")
        return text_config
    
    # 方法2：如果所有配置都是 vision，回退到关键词匹配
    logger.info("📝 所有配置都标记为vision，使用关键词匹配模式筛选文本模型")
    for cfg in config_list:
        if not _is_enabled(cfg):
            continue
        model_name = cfg.get('model', '').lower()
        # 排除vision/vl模型，只保留纯文本模型
        if not any(keyword in model_name for keyword in ['vision', 'vl']):
            text_config.append(cfg)
    
    if text_config:
        logger.info(f"✅ 使用文本模型（基于关键词）: {text_config[0].get('model')}")
        return text_config
    
    # 方法3：如果还是找不到，返回所有配置
    logger.warning("⚠️  未找到文本模型配置，将使用所有配置")
    return [cfg for cfg in config_list if _is_enabled(cfg)]


def _get_split_models(config_list):
    """获取需求拆分/PRD Knowledge 专用模型配置。"""
    split_config = []

    for cfg in config_list:
        if not _is_enabled(cfg):
            continue
        if cfg.get('model_type') == 'split':
            split_config.append(cfg)

    if split_config:
        logger.info(f"✅ 使用需求拆分模型: {split_config[0].get('model')}")
        return split_config

    logger.warning("⚠️  未找到需求拆分模型配置，将回退到普通文本模型")
    return _get_text_models(config_list)


def _clean_internal_fields(config_list):
    """
    清理配置中的内部字段，避免传递给 LLM API
    
    内部字段包括：
    - model_type: 仅用于筛选模型，不应传递给 API
    - comment: 仅用于配置说明，不应传递给 API
    
    Args:
        config_list: LLM配置列表
    
    Returns:
        list: 清理后的配置列表
    """
    cleaned_configs = []
    internal_fields = ['model_type', 'comment', 'enabled', 'api', 'authHeader', 'auth_header']
    
    for cfg in config_list:
        # 创建配置副本，避免修改原始配置
        cleaned_cfg = {k: v for k, v in cfg.items() if k not in internal_fields}
        cleaned_configs.append(cleaned_cfg)
    
    return cleaned_configs


def _is_enabled(cfg):
    return cfg.get('enabled') is not False


def get_model_info(config_list, model_type=None):
    """
    获取模型信息（用于日志和调试）
    
    Args:
        config_list: LLM配置列表
        model_type: 模型类型
    
    Returns:
        dict: 包含模型名称和数量的字典
    """
    models = get_models_by_type(config_list, model_type)
    
    return {
        'count': len(models),
        'models': [cfg.get('model', 'unknown') for cfg in models],
        'type': model_type or 'text'
    }
