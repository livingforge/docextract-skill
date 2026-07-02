"""docagent — カテゴライズ・要約結果を単一の集約 JSON に束ねるデータ操作 API。

docextract が出力する ``result.json`` を取り込み、カテゴリと要約を付与して
``store/library.json`` に集約する。CLI (``python -m docagent``) と、この
``Library`` を直接使う Python API の両方を提供する。
"""

from __future__ import annotations

from .facts import FactStore, default_item_types
from .store import (
    DEFAULT_CATEGORIES,
    DEFAULT_STORE,
    PACKAGED_CATEGORIES,
    DocAgentError,
    Library,
    default_categories,
)

__all__ = [
    "Library",
    "FactStore",
    "DocAgentError",
    "default_categories",
    "default_item_types",
    "DEFAULT_STORE",
    "DEFAULT_CATEGORIES",
    "PACKAGED_CATEGORIES",
]
