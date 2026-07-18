# 修正导入路径，指向具体的project.py文件
from .project.project import Project

# 确保其他模块可以被正确导入
__all__ = ['Project']
