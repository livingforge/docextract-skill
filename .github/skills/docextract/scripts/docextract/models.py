"""抽出結果を表すデータモデル。

すべての抽出要素は共通の dict 形式に変換され、JSON に直列化される。
- text  : 段落・見出しなどのテキストブロック
- table : 2次元配列 (rows) で表現される表
- image : ファイルとして保存された画像への参照とメタ情報
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TextElement:
    content: str
    style: Optional[str] = None
    location: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": "text", "content": self.content}
        if self.style:
            d["style"] = self.style
        if self.location:
            d["location"] = self.location
        return d


@dataclass
class TableElement:
    rows: list[list[str]]
    location: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": "table",
            "n_rows": len(self.rows),
            "n_cols": max((len(r) for r in self.rows), default=0),
            "rows": self.rows,
        }
        if self.location:
            d["location"] = self.location
        return d


@dataclass
class ImageElement:
    file: str  # 保存先への相対パス
    format: str
    width: Optional[int] = None
    height: Optional[int] = None
    ocr_text: Optional[str] = None  # OCR で読み取った画像内テキスト
    location: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": "image", "file": self.file, "format": self.format}
        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height
        if self.ocr_text:
            d["ocr_text"] = self.ocr_text
        if self.location:
            d["location"] = self.location
        return d


@dataclass
class ExtractionResult:
    source: str
    file_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    elements: list[Any] = field(default_factory=list)
    # 劣化系 (画像デコード失敗等) を握り潰さず痕跡として残すログ。
    # silent degradation を observable にするための構造化記録。
    degradations: list[dict[str, Any]] = field(default_factory=list)
    # 以下は extract() が抽出後に付与する同一性情報 (抽出器単体では未設定)。
    id: Optional[str] = None  # パスハッシュ由来の安定・衝突しない文書 ID
    source_abspath: Optional[str] = None  # ID の基準となる正規化済み絶対パス
    source_hash: Optional[str] = None  # source_abspath の sha256 先頭8桁
    content_hash: Optional[str] = None  # ファイル内容の sha256 (重複・改変検知)

    def note_degraded(self, stage: str, reason: str, **context: Any) -> dict[str, Any]:
        """劣化 (要素のスキップ等) を 1 件記録する。

        ``bare except: return`` で黙って落とす代わりに、どの段階 (stage) で・
        なぜ (reason)・どの対象 (context: page/image 等) を落としたかを構造化して
        残す。返した dict は呼び出し側が観測ログにも載せられる。
        """
        entry: dict[str, Any] = {"stage": stage, "reason": reason}
        entry.update({k: v for k, v in context.items() if v is not None})
        self.degradations.append(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        serialized = []
        for el in self.elements:
            d = el.to_dict()
            counts[d["type"]] = counts.get(d["type"], 0) + 1
            serialized.append(d)
        d: dict[str, Any] = {}
        # ID を先頭に置き、機械可読な文書として扱いやすくする。
        if self.id is not None:
            d["id"] = self.id
        d["source"] = self.source
        if self.source_abspath is not None:
            d["source_abspath"] = self.source_abspath
        if self.source_hash is not None:
            d["source_hash"] = self.source_hash
        if self.content_hash is not None:
            d["content_hash"] = self.content_hash
        d["file_type"] = self.file_type
        d["metadata"] = self.metadata
        d["summary"] = counts
        # 劣化があった場合のみ痕跡を残す (正常時は既存出力を変えない)。
        # 後工程が「この抽出は一部を取りこぼしている」と機械的に判定できる。
        if self.degradations:
            d["degraded"] = {
                "count": len(self.degradations),
                "items": self.degradations,
            }
        d["elements"] = serialized
        return d
