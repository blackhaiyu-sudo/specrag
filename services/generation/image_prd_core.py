"""Image PRD to knowledge-base source PRD core logic."""

from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List

from services.generation.llm_response_cleaner import strip_model_reasoning
from services.utils.notes_manager import extract_note_from_filename

logger = logging.getLogger(__name__)


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


def analyze_module_images(image_analyst, module_info, output_dir, notes_mgr=None, conv_logger=None):
    module_name = module_info["module_name"]
    logger.info("开始分析模块: %s", module_name)

    try:
        images_classification = {}
        classification_summary = {"BACKGROUND": 0, "FOCUS": 0, "RELATED": 0}
        image_type_tags = {
            "[背景]": "BACKGROUND",
            "[重点]": "FOCUS",
            "[关联]": "RELATED",
        }

        for img_info in module_info["images"]:
            filename = img_info.get("original_name") or img_info.get("filename") or img_info.get("name", "")
            img_type = "FOCUS"
            for tag, type_code in image_type_tags.items():
                if tag in filename:
                    img_type = type_code
                    break

            img_id = img_info.get("id") or img_info.get("name") or filename
            images_classification[img_id] = {"type": img_type, "filename": filename}
            classification_summary[img_type] += 1

        prompt = f"""你是资深产品经理和业务分析师，负责分析产品、流程或业务规则图片。

【当前模块】{module_name}
【图片总数】{len(module_info['images'])} 张

【图片详情】
"""

        for index, img_info in enumerate(module_info["images"], 1):
            img_note = extract_note_from_filename(img_info["filename"])
            prompt += f"\n图片 {index}: {img_info['filename']}\n"
            prompt += f"变更类型: {img_info['change_type']}\n"
            if img_note:
                prompt += f"📌 备注: {img_note}\n"

        prompt += """

【分析任务】
请逐张详细分析每个图片，提取需求信息。

重点关注：
1. 视觉标注（红框、箭头、文字备注等）
2. 交互细节（联动、反馈、状态变化）
3. 变更类型（新增/修改/删除/优化）
4. 如果图片有人工备注，优先关注备注内容

最后进行模块级整合分析，形成完整的交互逻辑描述。
"""

        content = [{"type": "text", "text": prompt}]
        for img_info in module_info["images"]:
            image_base64 = image_to_base64(img_info["path"])
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
            })

        messages = [{"role": "user", "content": content}]
        image_analysis = strip_model_reasoning(image_analyst.generate_reply(messages=messages))

        analysis_dir = os.path.join(output_dir, "logs", "image_analysis")
        os.makedirs(analysis_dir, exist_ok=True)
        module_name_sanitized = re.sub(r"[^\w\s-]", "", module_name).strip()
        analysis_file = os.path.join(analysis_dir, f"{module_name_sanitized}.md")
        with open(analysis_file, "w", encoding="utf-8") as file:
            file.write(f"# {module_name} - 图片分析结果\n\n{image_analysis}")

        return {
            "module_info": module_info,
            "image_analysis": image_analysis,
            "analysis_file": analysis_file,
            "prompt": prompt,
            "images_classification": images_classification,
            "classification_summary": classification_summary,
            "success": True,
        }
    except Exception as exc:
        logger.error("分析模块失败 %s: %s", module_name, exc, exc_info=True)
        return {
            "module_info": module_info,
            "image_analysis": f"❌ 分析失败: {str(exc)}",
            "success": False,
            "error": str(exc),
        }


def generate_version_prd(prd_generator, version_name, modules_results, output_dir, notes_mgr=None, conv_logger=None):
    logger.info("=" * 60)
    logger.info("开始版本级整合...")
    logger.info("版本名称: %s", version_name)

    successful_modules = [r for r in modules_results if r.get("success", False)]
    if not successful_modules:
        logger.error("没有成功的模块分析结果，跳过版本级整合")
        return None

    doc_notes = ""
    if notes_mgr and notes_mgr.has_notes():
        doc_notes = notes_mgr.get_notes_for_stage("需求文档补充")

    version_prd_prompt = "你是知识库源文档生成智能体，负责将 UI、流程或业务图片的分析结果整合成一份便于后续知识单元清洗的知识库源文档。\n\n"
    if doc_notes:
        version_prd_prompt += f"【项目背景和需求补充】\n{doc_notes}\n\n"

    total_classification = {"BACKGROUND": 0, "FOCUS": 0, "RELATED": 0}
    for result in successful_modules:
        for type_code, count in (result.get("classification_summary") or {}).items():
            total_classification[type_code] += count

    version_prd_prompt += (
        f"版本信息:\n- 版本名称: {version_name}\n- 功能模块数: {len(successful_modules)} 个\n"
        f"- 图片总数: {sum(len(r['module_info']['images']) for r in successful_modules)} 张\n\n"
    )

    if total_classification["BACKGROUND"] > 0 or total_classification["FOCUS"] > 0:
        images_by_content = {"BACKGROUND": [], "FOCUS": [], "RELATED": []}
        for module_result in successful_modules:
            for img_class in (module_result.get("images_classification") or {}).values():
                images_by_content[img_class["type"]].append(img_class["filename"])

        version_prd_prompt += f"图片分类 ({sum(total_classification.values())}张)\n\n"
        content_types = [
            ("BACKGROUND", "背景类", total_classification["BACKGROUND"]),
            ("FOCUS", "重点类", total_classification["FOCUS"]),
            ("RELATED", "关联类", total_classification["RELATED"]),
        ]
        for content_code, content_label, count in content_types:
            if count > 0:
                version_prd_prompt += f"{content_label} ({count}张):\n"
                for img_name in images_by_content[content_code]:
                    version_prd_prompt += f"- {img_name}\n"
                version_prd_prompt += "\n"

    version_prd_prompt += "---\n\n各图片分析结果:\n\n"
    for index, result in enumerate(successful_modules, 1):
        module_info = result["module_info"]
        module_name = module_info["module_name"]
        image_analysis = result["image_analysis"]
        images_list = module_info["images"]

        version_prd_prompt += f"\n## 模块 {index:02d}：{module_name}\n\n**包含图片**：{len(images_list)} 张\n"
        for img_index, img in enumerate(images_list, 1):
            version_prd_prompt += f"  {img_index}. {img['filename']}\n"
        version_prd_prompt += f"\n**分析内容**：\n{image_analysis}\n\n---\n\n"

    if doc_notes:
        version_prd_prompt += "\n【特别说明】\n请参考上述【项目背景和需求补充】中的需求目录和文档结构建议。\n\n"

    version_prd_prompt += "\n---\n\n请基于以上图片分析结果，生成完整的知识库源文档。\n"

    try:
        logs_dir = os.path.join(output_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        ai_prompt_file = os.path.join(logs_dir, "ai_prompt.md")
        with open(ai_prompt_file, "w", encoding="utf-8") as file:
            file.write("# 版本级整合 - AI输入Prompt\n\n")
            file.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n")
            file.write(version_prd_prompt)

        messages = [{"role": "user", "content": version_prd_prompt}]
        version_prd_document = strip_model_reasoning(prd_generator.generate_reply(messages=messages))

        ai_response_file = os.path.join(logs_dir, "ai_response.md")
        with open(ai_response_file, "w", encoding="utf-8") as file:
            file.write("# 版本级整合 - AI原始输出\n\n")
            file.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n")
            file.write(version_prd_document)

        prd_dir = os.path.join(output_dir, "prd")
        os.makedirs(prd_dir, exist_ok=True)
        version_prd_file = os.path.join(prd_dir, "version_prd.md")
        with open(version_prd_file, "w", encoding="utf-8") as file:
            file.write(f"# {version_name} - 知识库源文档\n\n{version_prd_document}")

        return {
            "prd_file": version_prd_file,
            "prd_content": version_prd_document,
            "prompt": version_prd_prompt,
            "success": True,
        }
    except Exception as exc:
        logger.error("知识库源文档生成失败: %s", exc, exc_info=True)
        return None
