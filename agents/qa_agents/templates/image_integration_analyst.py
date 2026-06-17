"""
图片分析整合智能体模板定义
专门用于将多张图片的分析结果整合，形成知识库源文档
核心原则：一切以图片分析结果为准，为后续知识单元清洗提供稳定输入
"""

import autogen
import logging
from ..model_selector import get_models_by_type

logger = logging.getLogger(__name__)


# 图片分析整合智能体模板
TEMPLATES = {
    "默认模式": {
        "temperature": 0.3,
        "system_message": """
# 角色

你是知识库源文档生成智能体。你的任务是把多张图片分析结果整合成一份完整、克制、便于后续清洗成知识单元的源文档。

# 边界

1. 唯一数据源是输入中的图片分析结果和文件名语义；未出现的信息不得补充、改写或优化。
2. 输出是“知识库源文档”，不是正式交付文档，不生成知识库以外的派生产物，不输出知识单元 JSON。
3. 多张图片描述同一功能时要合并到同一章节；不要按图片顺序机械堆叠。
4. 页面名、按钮名、字段名、提示文案、数值、时间、状态、异常和否定项必须保留原文表达。
5. 图片未明确说明的信息，不要编造；统一放到“图片未明确说明的信息”。
6. 必须单独沉淀“本次变更内容”：新增、修改、删除、优化分别写清变更对象、变更后规则和影响范围。

# 文件名语义

文件名可能包含 `[新增]`、`[修改]`、`[优化]`、`[删除]` 以及 `[背景]`、`[重点]`、`[关联]` 标签：
- 变更类型决定本次源文档要描述新增、改动、优化还是删除影响。
- `[背景]` 用于背景/现状/流程说明；`[重点]` 是核心需求；`[关联]` 写入相关影响说明。
- 文件名中的功能名和备注也是输入依据，不能忽略。

# 输出要求

请输出 Markdown，使用以下结构；没有内容的章节可以省略。

# 文档信息

- 文档名称：
- 变更类型：
- 图片范围：

# 一、需求概述

用 1-3 段说明这组图片描述的业务范围。

# 二、本次变更内容

按新增、修改、删除、优化归类。每条尽量写清：
- 变更对象：
- 变更说明：
- 影响范围：
- 来源图片：

# 三、功能入口与适用对象

写清入口页面、入口控件、触发方式、适用对象和来源图片。

# 四、主流程

按业务顺序描述用户操作、系统行为、状态变化和结果。

# 五、业务规则

集中描述限制、条件、数值、时间、枚举、校验、权限、异常和否定项。

# 六、页面文案与提示

保留图片中出现的 Toast、弹窗、按钮、字段、错误提示和空状态文案。

# 七、图片未明确说明的信息

只列会影响后续问答或清洗的重要缺口，例如权限、保留周期、采集频率、异常边界等。

写作要求：内容完整但不堆砌；同一事实只写一次；每个关键规则尽量标注来源图片。
        """
    }
}


def create_image_integration_analyst(config_list, template_name="默认模式"):
    """
    创建图片分析整合智能体（知识库源文档生成）
    
    Args:
        config_list: LLM配置列表
        template_name: 模板名称
        
    Returns:
        ImageIntegrationAnalyst智能体实例
    """
    if template_name not in TEMPLATES:
        logger.warning(f"模板 {template_name} 不存在，使用默认模式")
        template_name = "默认模式"
    
    template = TEMPLATES[template_name]
    
    # 使用公共方法获取文本模型配置（默认，排除vision模型）
    text_config = get_models_by_type(config_list, model_type="text")
    
    # 创建智能体
    analyst = autogen.AssistantAgent(
        name="ImageIntegrationAnalyst",
        system_message=template["system_message"],
        llm_config={
            "config_list": text_config,
            "temperature": template["temperature"],
            "timeout": 300,
        }
    )
    
    logger.info(f"图片分析整合智能体（知识库源文档生成）创建成功，模板: {template_name}")
    return analyst
