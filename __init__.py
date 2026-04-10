"""
aacode - AI Coding Assistant based on ReAct architecture
"""

__version__ = "1.5.0"
__author__ = "xiefujin"

if __package__ in (None, ""):
    # 直接 import aacode 时不导入，避免循环依赖
    # 用户应使用: from aacode.main import AICoder
    # 或: from aacode import AICoder (通过 __all__)
    pass
else:
    from .main import AICoder

    __all__ = ["AICoder", "__version__"]
