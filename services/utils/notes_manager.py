"""
备注管理器 - 用于管理和提取项目备注信息

支持：
1. 从 notes.txt 文件读取备注
2. 从图片文件名提取备注
3. 为不同阶段提供相应的备注内容
"""

import os
import re


class NotesManager:
    """
    备注管理器
    
    支持从 notes.txt 读取两类备注：
    - [全局]: 项目概述，所有阶段都能看到
    - [需求文档补充]: 用于图片分析、PRD 整合和知识库清洗
    """
    
    # 预定义的有效标签
    VALID_TAGS = {'全局', '需求文档补充'}
    
    def __init__(self, notes_file_path=None, notes_text=None):
        """
        初始化备注管理器
        
        Args:
            notes_file_path: notes.txt 文件路径
            notes_text: 直接提供备注文本（用于命令行或服务内部调用）
        """
        self.global_notes = ""
        self.doc_supplement = ""  # 需求文档补充
        
        if notes_text:
            self._parse_notes(notes_text)
        elif notes_file_path and os.path.exists(notes_file_path):
            with open(notes_file_path, 'r', encoding='utf-8') as f:
                self._parse_notes(f.read())
    
    def _parse_notes(self, text):
        """
        解析 notes.txt 内容
        
        格式：
        #%全局%#
        项目概述内容...
        
        #%需求文档补充%#
        需求相关内容...
        """
        sections = {}
        current_section = None
        current_content = []
        
        for line in text.split('\n'):
            # 检查是否是有效的标签行：#%标签%#
            if line.strip().startswith('#%') and line.strip().endswith('%#'):
                # 提取标签名（去掉 #% 和 %#）
                tag = line.strip()[2:-2].strip()
                
                # 只识别预定义的标签
                if tag in self.VALID_TAGS:
                    # 保存上一个部分
                    if current_section:
                        sections[current_section] = '\n'.join(current_content).strip()
                    
                    # 开始新部分
                    current_section = tag
                    current_content = []
                    continue  # 跳过标签行本身
            
            # 累积当前部分的内容
            if current_section:
                current_content.append(line)
        
        # 保存最后一个部分
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        
        # 提取各部分
        self.global_notes = sections.get('全局', '')
        self.doc_supplement = sections.get('需求文档补充', '')
    
    def get_notes_for_stage(self, stage):
        """
        获取指定阶段的备注
        
        Args:
            stage: "需求文档补充"
        
        Returns:
            str: 合并后的备注内容（包含全局说明 + 阶段补充）
            注意：不添加任何标题，保留用户在notes.txt中定义的原始格式
        """
        parts = []
        
        # 总是包含全局说明（不添加标题）
        if self.global_notes:
            parts.append(self.global_notes)
        
        # 添加阶段补充（不添加标题）
        if stage == "需求文档补充" and self.doc_supplement:
            parts.append(self.doc_supplement)
        
        return "\n\n".join(parts) if parts else ""
    
    def has_notes(self):
        """检查是否有任何备注"""
        return bool(self.global_notes or self.doc_supplement)
    
    def __repr__(self):
        return f"NotesManager(global={bool(self.global_notes)}, doc={bool(self.doc_supplement)})"


def extract_note_from_filename(filename):
    """
    从文件名提取备注
    
    格式：
    "01_功能描述#备注内容.png" → "备注内容"
    
    Args:
        filename: 文件名（包含扩展名）
    
    Returns:
        str: 提取的备注内容，如果没有备注则返回空字符串
    
    Examples:
        >>> extract_note_from_filename("01_WiFi配置#关注步骤数.png")
        '关注步骤数'
        >>> extract_note_from_filename("企业logo显示#注意位置和尺寸.png")
        '注意位置和尺寸'
        >>> extract_note_from_filename("普通图片.png")
        ''
    """
    # 去除扩展名
    name_without_ext = os.path.splitext(filename)[0]
    
    # 使用 # 分隔符
    if '#' in name_without_ext:
        parts = name_without_ext.split('#', 1)
        return parts[1].strip() if len(parts) > 1 else ""
    
    return ""  # 没有备注


def find_notes_file(directory):
    """
    在指定目录及其父目录中查找 notes.txt
    
    Args:
        directory: 起始目录
    
    Returns:
        str: notes.txt 的完整路径，如果没找到则返回 None
    """
    current_dir = os.path.abspath(directory)
    
    # 向上查找最多3级
    for _ in range(3):
        notes_path = os.path.join(current_dir, 'notes.txt')
        if os.path.exists(notes_path):
            return notes_path
        
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:  # 到达根目录
            break
        current_dir = parent_dir
    
    return None


if __name__ == "__main__":
    # 示例代码
    
    print("=== 文件名备注提取 ===")
    sample_filenames = [
        "01_WiFi配置#关注步骤数.png",
        "企业logo显示#注意位置和尺寸.png",
        "设备列表#关注排序规则.png",
        "普通图片.png",
        "包含井号的#issue#123.png",  # 只提取第一个#后的内容
    ]
    
    for filename in sample_filenames:
        note = extract_note_from_filename(filename)
        print(f"{filename:45} → '{note}'")
    
    print("\n=== NotesManager 示例 ===")
    sample_notes = """
#%全局%#
业务系统v1.2.0版本
涉及：列表页、批量导入、异常提示

#%需求文档补充%#
【项目背景】
v2.0.5遗留问题

【需求目录】
1. 新增功能
2. 优化项
"""
    
    mgr = NotesManager(notes_text=sample_notes)
    print(f"NotesManager: {mgr}")
    print(f"Has notes: {mgr.has_notes()}")
    
    print("\n--- 需求文档补充阶段 ---")
    doc_notes = mgr.get_notes_for_stage("需求文档补充")
    print(doc_notes[:200] + "..." if len(doc_notes) > 200 else doc_notes)
