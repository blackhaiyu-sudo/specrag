#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移：添加RequirementModule表（图片需求收集）
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database.models import Base, RequirementModule, DatabaseManager
from sqlalchemy import text

def upgrade():
    """执行迁移"""
    print("=" * 60)
    print("开始迁移：添加requirement_modules表")
    print("=" * 60)
    
    # 初始化数据库管理器
    db_manager = DatabaseManager()
    db_manager.initialize()
    
    # 创建表
    engine = db_manager.get_engine()
    
    # 只创建RequirementModule表
    RequirementModule.__table__.create(engine, checkfirst=True)
    
    print("✅ requirement_modules表创建成功")
    
    # 验证表结构
    connection = engine.connect()
    result = connection.execute(text("PRAGMA table_info(requirement_modules)"))
    columns = result.fetchall()
    
    print(f"\n表结构验证（共{len(columns)}个字段）:")
    for col in columns:
        print(f"  - {col[1]}: {col[2]}")
    
    connection.close()
    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)

def downgrade():
    """回滚迁移"""
    print("=" * 60)
    print("开始回滚：删除requirement_modules表")
    print("=" * 60)
    
    db_manager = DatabaseManager()
    db_manager.initialize()
    engine = db_manager.get_engine()
    
    RequirementModule.__table__.drop(engine, checkfirst=True)
    
    print("✅ requirement_modules表已删除")
    print("=" * 60)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='RequirementModule表迁移')
    parser.add_argument('action', choices=['upgrade', 'downgrade'], help='迁移操作')
    
    args = parser.parse_args()
    
    if args.action == 'upgrade':
        upgrade()
    else:
        downgrade()

