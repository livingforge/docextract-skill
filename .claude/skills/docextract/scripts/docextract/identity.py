"""文書の安定 ID とソースパスの正規化を一元管理するモジュール。

ID は「入力ファイルの正規化済み絶対パス」から決定論的に導く:

    <safe_stem>_<ext>_<hash8>

- ``safe_stem`` : ファイル名 (拡張子なし) をファイルシステム安全化した芯
- ``ext``       : 拡張子 (小文字・ドットなし)
- ``hash8``     : 正規化済み絶対パスの sha256 先頭 8 桁

こうすることで、別フォルダにある同名ファイル (``2024/議事録.docx`` と
``2025/議事録.docx``) でもパスが違えば ID が衝突しない。同じパスを再抽出した
ときは同じ ID になる (冪等)。

**この関数が唯一の ID 生成箇所**である。docextract の出力フォルダ名も
docagent のストア ID も必ずここを通し、両者が一致することを保証する
(ベース名だけから作っていた旧方式の「別フォルダ同名で衝突」「フォルダ名と
ID の不一致」というバグを構造的に排除する)。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# 絶対パスハッシュから採る桁数。8 桁 (32bit) あれば通常規模の資料群で
# 衝突確率は無視できる。
HASH_LEN = 8


def canonical_source(path: str | Path) -> str:
    """ID 生成の基準となる正規化済み絶対パス (posix 表記) を返す。

    相対・絶対のどちらで渡されても ``resolve()`` で同じ絶対パスへ畳むため、
    同一ファイルは常に同じキーになる。
    """
    return Path(path).resolve().as_posix()


def _safe_stem(stem: str) -> str:
    """ファイル名の芯を FS/URL で扱いやすい文字だけにする (空なら ``doc``)。"""
    s = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in stem)
    return s or "doc"


def source_hash(source_key: str) -> str:
    """正規化済みソースキーの sha256 先頭 ``HASH_LEN`` 桁。"""
    return hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:HASH_LEN]


def doc_id(path: str | Path, source_key: str | None = None) -> str:
    """入力ファイルパスから安定・衝突しない文書 ID を作る。

    ``source_key`` を渡せば正規化を省いてそのキーでハッシュする
    (extract() が resolve 済みのキーを使い回すための最適化)。
    """
    p = Path(path)
    key = source_key if source_key is not None else canonical_source(p)
    stem = _safe_stem(p.stem or p.name)
    ext = p.suffix.lstrip(".").lower()
    base = f"{stem}_{ext}" if ext else stem
    return f"{base}_{source_hash(key)}"


def content_hash(path: str | Path) -> str:
    """ファイル内容の sha256 (全 64 桁)。内容重複・改変の検知に使う。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
