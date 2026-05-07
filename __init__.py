"""
aacode - AI Coding Assistant based on ReAct architecture
"""

__version__ = "1.7.1"
__author__ = "xiefujin"

# 修复：无论 __package__ 是否为空，都要确保包可以被导入
# 当使 with  python -c 或作为独立脚本execute时，__package__ 为 None
try:
    from .main import AICoder
    __all__ = ["AICoder", "__version__"]
except ImportError:
    # 如果是作为顶层包导入（python -c 场景）
    import sys
    from pathlib import Path
    
    # Get 包所在目录
    pkg_dir = Path(__file__).parent
    
    # 添加父目录到 sys.path（这样可以导入 aacode.core 等）
    if str(pkg_dir.parent) not in sys.path:
        sys.path.insert(0, str(pkg_dir.parent))
    
    # 尝试再次导入
    try:
        from main import AICoder
        __all__ = ["AICoder", "__version__"]
    except ImportError:
        # 如果还是失败，至少定义 __all__ 避免其他问题
        __all__ = ["__version__"]
