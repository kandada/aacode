"""
i18n 翻译模块
零外部依赖，纯 Python dict 实现
"""
import os
from typing import Dict


_translations: Dict[str, Dict[str, str]] = {}
_current_lang: str = "en"


def init(lang: str = None):
    """初始化语言，优先参数 → 环境变量 → 默认 en"""
    global _current_lang
    from ._dict import TRANSLATIONS
    _translations.clear()
    _translations.update(TRANSLATIONS)
    if lang:
        _current_lang = lang
    else:
        _current_lang = os.getenv("AACODE_LANG", "en")
    if _current_lang not in ("en", "zh"):
        _current_lang = "en"


def t(key: str, **kwargs) -> str:
    """获取翻译，支持格式化参数"""
    entry = _translations.get(key, {})
    text = entry.get(_current_lang) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def lang() -> str:
    return _current_lang
