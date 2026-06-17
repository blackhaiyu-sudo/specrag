"""Image PRD import helper for the knowledge-base pipeline."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from database.models import DatabaseManager, RequirementModule

logger = logging.getLogger(__name__)


class ImagePipelineService:
    """Generate a knowledge-base source PRD from an image requirement module."""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.db_manager.initialize()

    def _stage1_analyze_images(self, module_id: str, pipeline_logger) -> Dict[str, Dict[str, Any]]:
        """Analyze all images of one module with the vision agent."""
        from agents.qa_agents.factory import QAAgentFactory
        from services.generation.image_prd_core import analyze_module_images

        module = self._get_module(module_id)
        stage_logger = _stage_logger(pipeline_logger, "stage1")

        config_list = self._load_config()
        image_analyst = QAAgentFactory(config_list=config_list).create_image_analyst()

        output_dir = self._get_output_dir(module_id)
        os.makedirs(output_dir, exist_ok=True)

        images_info = []
        for img in module.images or []:
            original_name = img.get("original_name") or img.get("name") or os.path.basename(img.get("path", ""))
            images_info.append({
                "filename": original_name,
                "path": img.get("path"),
                "change_type": self._get_change_type(module, original_name),
            })

        module_info = {
            "module_name": module.name,
            "description": module.description or "",
            "images": images_info,
        }

        stage_logger.info("准备分析 %s 张图片", len(images_info))
        notes_mgr = self._get_notes_manager(module)
        started_at = time.time()
        analysis_result = analyze_module_images(
            image_analyst=image_analyst,
            module_info=module_info,
            output_dir=output_dir,
            notes_mgr=notes_mgr,
            conv_logger=None,
        )
        duration = time.time() - started_at
        _log_metric(pipeline_logger, "analyze_images", duration)

        if not analysis_result.get("success"):
            raise RuntimeError(f"图片分析失败: {analysis_result.get('error', '未知错误')}")

        analysis_text = analysis_result.get("image_analysis", "")
        stage_logger.info("图片分析完成，内容长度 %s，耗时 %.2fs", len(analysis_text), duration)
        _save_ai_response(
            pipeline_logger,
            agent_name="ImageAnalyst",
            prompt=analysis_result.get("prompt") or f"分析模块: {module.name}",
            response=analysis_text,
            metadata={
                "module_name": module.name,
                "images_count": len(images_info),
                "duration": duration,
                "classification_summary": analysis_result.get("classification_summary"),
            },
        )

        analyses_dict = {module.name: analysis_result}
        self._update_module(module_id, module_analyses=json.dumps(analyses_dict, ensure_ascii=False))
        return analyses_dict

    def _stage2_generate_prd(self, module_id: str, analyses: Dict[str, Dict[str, Any]], pipeline_logger) -> tuple[str, str]:
        """Integrate image analysis into a knowledge-base source PRD."""
        from agents.qa_agents.factory import QAAgentFactory
        from services.generation.image_prd_core import generate_version_prd

        module = self._get_module(module_id)
        stage_logger = _stage_logger(pipeline_logger, "stage2")

        config_list = self._load_config()
        prd_generator = QAAgentFactory(config_list=config_list).create_image_integration_analyst()

        modules_results = []
        for _, analysis_result in analyses.items():
            if not analysis_result.get("success"):
                continue
            result = {
                "module_info": analysis_result.get("module_info", {}),
                "image_analysis": analysis_result.get("image_analysis", ""),
                "success": True,
            }
            if "classification_summary" in analysis_result:
                result["classification_summary"] = analysis_result["classification_summary"]
            if "images_classification" in analysis_result:
                result["images_classification"] = analysis_result["images_classification"]
            modules_results.append(result)

        stage_logger.info("准备生成知识库源文档，成功模块数 %s", len(modules_results))
        output_dir = self._get_output_dir(module_id)
        notes_mgr = self._get_notes_manager(module)
        started_at = time.time()
        prd_result = generate_version_prd(
            prd_generator=prd_generator,
            version_name=module.name,
            modules_results=modules_results,
            output_dir=output_dir,
            notes_mgr=notes_mgr,
            conv_logger=None,
        )
        duration = time.time() - started_at
        _log_metric(pipeline_logger, "generate_prd", duration)

        if not prd_result or not prd_result.get("success"):
            raise RuntimeError("知识库源文档生成失败：请检查模型配置、网络和账号余额")

        prd_file = prd_result.get("prd_file")
        prd_content = prd_result.get("prd_content", "")
        if not prd_file or not os.path.exists(prd_file):
            raise RuntimeError(f"知识库源文档文件生成失败：文件不存在 {prd_file}")

        stage_logger.info("知识库源文档生成完成，长度 %s，耗时 %.2fs", len(prd_content), duration)
        _save_ai_response(
            pipeline_logger,
            agent_name="ImageIntegrationAnalyst",
            prompt=prd_result.get("prompt") or f"整合 {len(modules_results)} 个模块生成知识库源文档",
            response=prd_content,
            metadata={
                "version_name": module.name,
                "modules_count": len(modules_results),
                "duration": duration,
            },
        )

        self._update_module(
            module_id,
            prd_version_content=prd_content,
            prd_final_content=prd_content,
            prd_file_path=prd_file,
        )
        return prd_content, prd_file

    def _get_module(self, module_id: str) -> RequirementModule:
        session = self.db_manager.get_session()
        try:
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            if not module:
                raise ValueError(f"需求模块不存在: {module_id}")
            session.expunge(module)
            return module
        finally:
            session.close()

    def _update_module(self, module_id: str, **kwargs) -> None:
        session = self.db_manager.get_session()
        try:
            module = session.query(RequirementModule).filter_by(id=module_id).first()
            if not module:
                raise ValueError(f"需求模块不存在: {module_id}")
            for key, value in kwargs.items():
                setattr(module, key, value)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _load_config(self) -> List[Dict[str, Any]]:
        config_path = os.environ.get("AUTOGEN_CONFIG_PATH") or os.path.join(
            os.path.dirname(__file__),
            "../../config/OAI_CONFIG_LIST",
        )
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        with open(config_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def _get_notes_manager(self, module: RequirementModule) -> Optional["NotesManager"]:
        from services.utils.notes_manager import NotesManager

        if not module.notes_requirement:
            return None

        output_dir = self._get_output_dir(module.id)
        notes_file = os.path.join(output_dir, "notes.md")
        with open(notes_file, "w", encoding="utf-8") as file:
            if module.notes_requirement:
                file.write("## 需求文档补充\n\n")
                file.write(module.notes_requirement)
                file.write("\n\n")
        return NotesManager(notes_file)

    def _get_change_type(self, module: RequirementModule, filename: str) -> str:
        import re

        match = re.match(r"^\[([^\]]+)\]", filename or "")
        if match:
            return match.group(1)

        if module.notes:
            try:
                notes_dict = json.loads(module.notes) if isinstance(module.notes, str) else module.notes
                file_note = notes_dict.get(filename, {})
                change_type = file_note.get("change_type", "未指定")
                if change_type != "未指定":
                    return change_type
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        return "未指定"

    def _get_output_dir(self, module_id: str) -> str:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        output_dir = os.path.join(project_root, "outputs", "image_prd", f"module_{module_id}")
        os.makedirs(output_dir, exist_ok=True)
        return output_dir


def _stage_logger(pipeline_logger, stage_name: str):
    return getattr(pipeline_logger, "stage_loggers", {}).get(stage_name, logger)


def _log_metric(pipeline_logger, name: str, duration: float) -> None:
    if hasattr(pipeline_logger, "log_performance_metric"):
        pipeline_logger.log_performance_metric(name, duration)


def _save_ai_response(pipeline_logger, *, agent_name: str, prompt: str, response: str, metadata: Dict[str, Any]) -> None:
    if hasattr(pipeline_logger, "save_ai_response"):
        pipeline_logger.save_ai_response(
            agent_name=agent_name,
            prompt=prompt,
            response=response,
            metadata=metadata,
        )
