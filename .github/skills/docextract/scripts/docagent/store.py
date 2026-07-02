"""集約 JSON ストア (ライブラリ) の読み書きと操作を担う中核モジュール。

docextract が各文書ごとに出力する ``result.json`` を取り込み、カテゴライズ・要約の
結果を付与して、**単一の集約 JSON** (既定 ``.docextract/store/library.json``) に束ねる。

- データ操作:  add / update / set_category / set_summary / remove
- データ参照:  get / list / query / stats / export

CLI (``docagent/cli.py``) と Python API の両方からこの ``Library`` を使う。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import get_close_matches
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from docextract import paths as _paths

SCHEMA_VERSION = 1

# 既定の保存先。docextract と同じ基点 (.docextract/、env DOCEXTRACT_HOME で変更可)
# 配下の store/ にまとめ、ホストプロジェクトの store/ と衝突しないようにする。
# CLI / API から個別に上書きも可能。
DEFAULT_STORE = _paths.store_path()
DEFAULT_CATEGORIES = _paths.categories_path()

# 既定タクソノミーの定義ファイル (パッケージ同梱)。コードにはハードコードしない。
# 実行時は store/categories.json (利用者が各自編集できる) が存在すればそちらが優先。
PACKAGED_CATEGORIES = Path(__file__).resolve().parent / "categories.json"

# 分析未完了を表す既定カテゴリ (タクソノミー外の一時値)。
UNCLASSIFIED = "未分類"


def _now() -> str:
    """ISO8601 (UTC) のタイムスタンプ文字列。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def doc_id_from_source(source: str) -> str:
    """入力ファイル名から安定した ID を作る (docextract の出力フォルダ名と一致)。

    例: ``report.docx`` -> ``report_docx`` / ``a/b/売上.xlsx`` -> ``売上_xlsx``
    """
    p = Path(source)
    stem = p.stem or p.name
    ext = p.suffix.lstrip(".").lower()
    base = f"{stem}_{ext}" if ext else stem
    # ファイルシステム・URL で扱いやすいよう空白等を潰す。
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in base)


class DocAgentError(Exception):
    """docagent 由来のユーザー向けエラー。"""


def default_categories() -> list[str]:
    """パッケージ同梱の categories.json から既定タクソノミーを読む。"""
    cats = _read_categories_file(PACKAGED_CATEGORIES)
    if cats is None:
        raise DocAgentError(
            f"既定カテゴリ定義が読めません: {PACKAGED_CATEGORIES}。"
            " docagent パッケージに categories.json が同梱されているか確認してください"
        )
    return cats


@dataclass
class Library:
    """集約 JSON ストア本体。

    ファイルとの入出力は :meth:`load` / :meth:`save` が担い、それ以外の操作は
    メモリ上の ``documents`` に対して行う。
    """

    path: Path
    categories_path: Path | None = None
    version: int = SCHEMA_VERSION
    categories: list[str] = field(default_factory=default_categories)
    documents: list[dict[str, Any]] = field(default_factory=list)

    # ── 入出力 ────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str | Path, categories_path: str | Path | None = None) -> "Library":
        """ストアを読み込む。無ければ空のライブラリを返す (ファイルは作らない)。"""
        path = Path(path)
        cats_path = Path(categories_path) if categories_path else path.parent / "categories.json"
        categories = _load_categories(cats_path)

        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            lib = cls(
                path=path,
                categories_path=cats_path,
                version=data.get("version", SCHEMA_VERSION),
                categories=data.get("categories") or categories,
                documents=data.get("documents", []),
            )
            # categories.json が別に存在すればそちらを正とする。
            if cats_path.exists():
                lib.categories = categories
            return lib
        return cls(path=path, categories_path=cats_path, categories=categories)

    def save(self) -> None:
        """ストアを JSON として書き出す (親ディレクトリは自動作成)。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "categories": self.categories,
            "documents": self.documents,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # ── 参照 ──────────────────────────────────────────────────
    def get(self, doc_id: str) -> dict[str, Any]:
        for d in self.documents:
            if d["id"] == doc_id:
                return d
        # エラー文に「次の一手」を含める: エージェントが自力で立ち直れるように。
        close = get_close_matches(doc_id, [d["id"] for d in self.documents], n=3, cutoff=0.5)
        hint = f" 似た ID: {', '.join(close)}。" if close else ""
        raise DocAgentError(
            f"ID '{doc_id}' の文書は登録されていません。{hint}"
            f" 登録済み ID の一覧: python -m docagent list"
        )

    def find(self, doc_id: str) -> dict[str, Any] | None:
        for d in self.documents:
            if d["id"] == doc_id:
                return d
        return None

    def query(
        self,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        text: str | None = None,
    ) -> list[dict[str, Any]]:
        """条件でフィルタして文書リストを返す。"""
        results = self.documents
        if category:
            results = [d for d in results if d.get("category") == category]
        if status:
            results = [d for d in results if d.get("status") == status]
        if keyword:
            k = keyword.lower()
            results = [d for d in results if any(k in (kw or "").lower() for kw in d.get("keywords", []))]
        if text:
            t = text.lower()
            results = [d for d in results if t in _searchable_text(d)]
        return list(results)

    def stats(self) -> dict[str, Any]:
        """カテゴリ別・ステータス別の件数などの集計。"""
        by_category: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for d in self.documents:
            by_category[d.get("category") or UNCLASSIFIED] = by_category.get(d.get("category") or UNCLASSIFIED, 0) + 1
            by_status[d.get("status", "registered")] = by_status.get(d.get("status", "registered"), 0) + 1
        return {
            "total": len(self.documents),
            "by_category": by_category,
            "by_status": by_status,
        }

    def export(self) -> dict[str, Any]:
        """集約 JSON 全体を dict で返す (データ参照)。"""
        return {
            "version": self.version,
            "categories": self.categories,
            "documents": self.documents,
        }

    def extract_text(self, doc_id: str, max_chars: int | None = None) -> dict[str, Any]:
        """result.json から本文テキストだけを組み立てて返す (要約用の軽量ビュー)。

        座標・レイアウト等の JSON フィールドを落とし、テキスト全文・表の全行・
        画像 OCR をプレーンテキストに整形する。モデルに渡すトークン量を
        result.json 全体の Read より大幅に抑えるための参照系。
        """
        doc = self.get(doc_id)
        result_path = Path(doc.get("result_path") or "")
        if not result_path.exists():
            raise DocAgentError(
                f"result.json が見つかりません: {result_path}。"
                f" docextract で再抽出してから python -m docagent prep <result.json>"
                f" で登録し直してください"
            )
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        text = _render_text(result)
        total = len(text)
        truncated = max_chars is not None and total > max_chars
        if truncated:
            text = text[:max_chars]
        return {
            "id": doc_id,
            "source": doc.get("source"),
            "total_chars": total,
            "truncated": truncated,
            "text": text,
        }

    def prep(self, target: str, max_chars: int | None = 8000) -> dict[str, Any]:
        """分析準備を 1 コマンドに集約する (エージェントの手順を減らすための複合操作)。

        ``target`` が result.json のパスなら登録 (既存なら抽出フィールドのみ更新し、
        分析結果は保持) してストアを保存、登録済み ID ならそのまま参照する。
        返り値に分類・要約へ必要な材料 (カテゴリ一覧・preview・本文抜粋・次の一手)
        をすべて含めるので、呼び出し側は categories / add / get / text を
        個別に叩く必要がない。
        """
        path = Path(target)
        if path.is_file():
            doc = self.add_from_result(path, overwrite=True)
            self.save()
        else:
            found = self.find(target)
            if found is None:
                raise DocAgentError(
                    f"'{target}' は登録済みの文書 ID でも result.json のパスでもありません。"
                    f" 登録済み ID の一覧: python -m docagent list"
                )
            doc = found

        analyzed = doc.get("status") == "analyzed"
        payload: dict[str, Any] = {
            "id": doc["id"],
            "source": doc.get("source"),
            "file_type": doc.get("file_type"),
            "status": doc.get("status"),
            "already_analyzed": analyzed,
            "categories": list(self.categories),
            "metadata": doc.get("metadata", {}),
            "stats": doc.get("stats", {}),
            "preview": doc.get("preview", ""),
        }
        if analyzed:
            payload["category"] = doc.get("category")
            payload["summary"] = doc.get("summary")
            payload["keywords"] = doc.get("keywords", [])
            payload["next_action"] = (
                "解析済み。再解析を明示的に指示されていない限り、"
                "この文書は処理せず「解析済みのためスキップ」と報告する"
            )
            return payload
        try:
            text = self.extract_text(doc["id"], max_chars=max_chars)
            payload["text"] = text["text"]
            payload["text_truncated"] = text["truncated"]
            payload["text_total_chars"] = text["total_chars"]
        except DocAgentError:
            # result.json が失われていても preview だけで判断できるようにする。
            payload["text"] = None
        payload["next_action"] = (
            "categories から 1 つ選び、日本語 3〜5 文の要約を書いて保存: "
            f'python -m docagent set {doc["id"]} --category "<カテゴリ>"'
            ' --summary "<要約>" --keywords "<語1,語2,...>"'
        )
        return payload

    # ── 操作 ──────────────────────────────────────────────────
    def add_from_result(self, result_path: str | Path, overwrite: bool = False) -> dict[str, Any]:
        """docextract の result.json を取り込み、文書エントリを登録する。

        カテゴリ・要約は未設定 (status=registered) で登録し、後から
        :meth:`set_category` / :meth:`set_summary` で埋める。
        """
        result_path = Path(result_path)
        result = _load_result_json(result_path)

        source = result.get("source", result_path.stem)
        doc_id = doc_id_from_source(source)
        existing = self.find(doc_id)
        if existing and not overwrite:
            raise DocAgentError(
                f"ID '{doc_id}' は既に登録済みです。上書き登録するには:"
                f" python -m docagent add {result_path} --overwrite"
                f" (分析結果は保持されます)。分析の準備なら:"
                f" python -m docagent prep {result_path}"
            )

        entry = {
            "id": doc_id,
            "source": source,
            "file_type": result.get("file_type"),
            "result_path": str(result_path).replace("\\", "/"),
            "metadata": result.get("metadata", {}),
            "stats": result.get("summary", {}),
            "preview": _build_preview(result),
            "category": None,
            "summary": None,
            "keywords": [],
            "status": "registered",
            "added_at": existing["added_at"] if existing else _now(),
            "updated_at": _now(),
        }
        if existing:
            # 既存の分析結果は保持しつつ抽出由来のフィールドのみ更新。
            entry["category"] = existing.get("category")
            entry["summary"] = existing.get("summary")
            entry["keywords"] = existing.get("keywords", [])
            entry["status"] = existing.get("status", "registered")
            self.documents[self.documents.index(existing)] = entry
        else:
            self.documents.append(entry)
        return entry

    def set_category(self, doc_id: str, category: str, force: bool = False) -> dict[str, Any]:
        """カテゴリを設定する。既定ではタクソノミー内の値に正規化して許可。

        LLM は「見積」「議事録 」「『契約・法務』」のように表記が揺れた値を返す
        ことがある。厳密一致で弾く代わりに :func:`_resolve_category` で正式名へ
        寄せ、寄せられないときだけ拒否する（``force`` 時は正規化のみで任意許可）。
        """
        doc = self.get(doc_id)
        doc["category"] = _resolve_category(category, self.categories, force=force)
        doc["updated_at"] = _now()
        self._refresh_status(doc)
        return doc

    def set_summary(
        self, doc_id: str, summary: str, keywords: Iterable[str] | None = None
    ) -> dict[str, Any]:
        """要約 (と任意のキーワード) を設定する。"""
        doc = self.get(doc_id)
        doc["summary"] = summary
        if keywords is not None:
            doc["keywords"] = [k.strip() for k in keywords if k.strip()]
        doc["updated_at"] = _now()
        self._refresh_status(doc)
        return doc

    def update(
        self,
        doc_id: str,
        category: str | None = None,
        summary: str | None = None,
        keywords: Iterable[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """カテゴリ・要約・キーワードをまとめて更新する。"""
        doc = self.get(doc_id)
        if category is not None:
            doc["category"] = _resolve_category(category, self.categories, force=force)
        if summary is not None:
            doc["summary"] = summary
        if keywords is not None:
            doc["keywords"] = [k.strip() for k in keywords if k.strip()]
        doc["updated_at"] = _now()
        self._refresh_status(doc)
        return doc

    def remove(self, doc_id: str) -> dict[str, Any]:
        doc = self.get(doc_id)
        self.documents.remove(doc)
        return doc

    # ── カテゴリ管理 ──────────────────────────────────────────
    def add_category(self, name: str) -> None:
        if name not in self.categories:
            self.categories.append(name)

    def remove_category(self, name: str) -> None:
        if name in self.categories:
            self.categories.remove(name)

    def save_categories(self) -> None:
        if self.categories_path:
            self.categories_path.parent.mkdir(parents=True, exist_ok=True)
            self.categories_path.write_text(
                json.dumps({"categories": self.categories}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    # ── 内部 ──────────────────────────────────────────────────
    @staticmethod
    def _refresh_status(doc: dict[str, Any]) -> None:
        """カテゴリと要約が揃ったら status を analyzed に上げる。"""
        if doc.get("category") and doc.get("summary"):
            doc["status"] = "analyzed"
        else:
            doc["status"] = "registered"


# カテゴリ名の外側を囲みがちな引用符・括弧 (全角半角)。LLM が『契約・法務』の
# ように装飾して返す揺れを剥がすため。
_CATEGORY_WRAPPERS = "「」『』｢｣（）()【】[]〈〉《》\"'`"


def _normalize_category_text(raw: str) -> str:
    """カテゴリ名の表記揺れを畳む: NFKC・前後空白・外側の囲み記号を除去。"""
    s = unicodedata.normalize("NFKC", raw).strip()
    # 外側の囲み記号を内側が変わらなくなるまで繰り返し剥がす (『議事録』→ 議事録)。
    prev = None
    while prev != s and len(s) >= 2:
        prev = s
        s = s.strip(_CATEGORY_WRAPPERS).strip()
    return s


def _loose_category(s: str) -> str:
    """比較用のゆるい形: 区切り (中黒・スラッシュ・空白) を除いた芯だけにする。"""
    return re.sub(r"[・/／\s]", "", s)


def _resolve_category(raw: str, categories: list[str], force: bool = False) -> str:
    """入力カテゴリ名をタクソノミー内の正式名へ解決する。

    表記揺れは吸収し、判断がつかないときだけ :class:`DocAgentError` で拒否する。
    解決は信頼度の高い順に試す:

    1. 正規化 (NFKC・空白・囲み記号除去) 後の完全一致
    2. 区切り記号を無視したゆるい一致 (見積／費用 ↔ 見積・費用)
    3. 一意な前方一致 (見積 → 見積・費用。候補が複数なら不採用)
    4. difflib による高信頼の近似一致 (cutoff=0.8)

    ``force`` 時はタクソノミーに合わせず、正規化した値をそのまま採用する
    （任意カテゴリを明示的に許可する用途）。
    """
    norm = _normalize_category_text(raw)
    if force:
        return norm or raw
    # 1. 正規化後の完全一致
    for c in categories:
        if norm == _normalize_category_text(c):
            return c
    loose = _loose_category(norm)
    # 2. 区切りを無視したゆるい一致
    for c in categories:
        if loose and loose == _loose_category(_normalize_category_text(c)):
            return c
    # 3. 一意な前方一致 (どちらかがもう一方の接頭辞)
    prefix_hits = [
        c
        for c in categories
        if loose
        and (
            (lc := _loose_category(_normalize_category_text(c))).startswith(loose)
            or loose.startswith(lc)
        )
    ]
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    # 4. 近似一致 (正規化した候補集合に対して)
    norm_map = {_normalize_category_text(c): c for c in categories}
    close = get_close_matches(norm, list(norm_map), n=1, cutoff=0.8)
    if close:
        return norm_map[close[0]]
    raise DocAgentError(_unknown_category_message(raw, categories))


def _unknown_category_message(category: str, categories: list[str]) -> str:
    """タクソノミー外カテゴリの拒否メッセージ (正しい選択肢を必ず添える)。"""
    close = get_close_matches(category, categories, n=1, cutoff=0.4)
    hint = f" もしかして: {close[0]}。" if close else ""
    return (
        f"カテゴリ '{category}' はタクソノミーにありません。{hint}"
        f" この一覧から選び直してください: {', '.join(categories)}"
    )


# docextract が扱う元ファイルの拡張子。これらが result.json の代わりに直接
# 渡されるのは「抽出ステップを飛ばした」典型的な事故なので、専用の案内を出す。
_RAW_DOC_SUFFIXES = {
    ".docx", ".xlsx", ".xlsm", ".pptx", ".pdf", ".doc", ".xls", ".ppt",
}


def _load_result_json(result_path: Path) -> dict[str, Any]:
    """docextract の result.json を読み込む (取り込み系の共通入口)。

    元ファイルの直接渡し・壊れた JSON・想定外の形式を、生の JSONDecodeError では
    なく「次の一手」を添えた :class:`DocAgentError` に変換する。docextract を
    通さずに Excel 等をそのまま渡す事故を、その場で立ち直れる形で弾くための関門。
    """
    if not result_path.exists():
        raise DocAgentError(f"result.json が見つかりません: {result_path}")
    if result_path.suffix.lower() in _RAW_DOC_SUFFIXES:
        raise DocAgentError(
            f"result.json ではなく元ファイルが渡されました: {result_path}。"
            " docagent が受け取るのは docextract が出力した result.json です。"
            " 先に抽出してください: "
            f"python -m docextract {result_path}"
            " → 生成された .docextract/output/<名前>_<拡張子>/result.json を渡す"
        )
    try:
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise DocAgentError(
            f"result.json として読み込めません: {result_path} ({e})。"
            " docextract が出力した result.json か確認してください"
            "（元ファイルを直接渡していませんか？ その場合は先に"
            " python -m docextract で抽出してください）"
        ) from e
    if not isinstance(result, dict) or "elements" not in result:
        raise DocAgentError(
            f"docextract の result.json 形式ではありません（'elements' がありません）: "
            f"{result_path}"
        )
    return result


def _load_categories(cats_path: Path) -> list[str]:
    cats = _read_categories_file(cats_path)
    return cats if cats is not None else default_categories()


def _read_categories_file(path: Path) -> list[str] | None:
    """categories.json を読んでカテゴリ一覧を返す。無効・不存在なら None。"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    cats = data.get("categories") if isinstance(data, dict) else data
    return list(cats) if cats else None


def _searchable_text(doc: dict[str, Any]) -> str:
    parts = [
        doc.get("source", ""),
        doc.get("summary") or "",
        " ".join(doc.get("keywords", [])),
        doc.get("preview", ""),
        json.dumps(doc.get("metadata", {}), ensure_ascii=False),
    ]
    return " ".join(parts).lower()


def _render_text(result: dict[str, Any]) -> str:
    """elements をプレーンテキストへ整形する (text 全文・表の全行・画像 OCR)。"""
    lines: list[str] = []
    for el in result.get("elements", []):
        t = el.get("type")
        if t == "text" and el.get("content"):
            lines.append(el["content"])
        elif t == "table" and el.get("rows"):
            lines.append("[表]")
            lines.extend(" | ".join(str(c) for c in row) for row in el["rows"])
        elif t == "image" and el.get("ocr_text"):
            lines.append("[画像OCR] " + el["ocr_text"])
    return "\n".join(lines)


def _build_preview(result: dict[str, Any], max_chars: int = 600) -> str:
    """result.json 先頭のテキスト・OCR を連結し、分析の手がかりになる抜粋を作る。"""
    chunks: list[str] = []
    for el in result.get("elements", []):
        if el.get("type") == "text" and el.get("content"):
            chunks.append(el["content"])
        elif el.get("type") == "table" and el.get("rows"):
            head = el["rows"][0] if el["rows"] else []
            chunks.append("[表] " + " | ".join(str(c) for c in head))
        elif el.get("type") == "image" and el.get("ocr_text"):
            chunks.append("[画像OCR] " + el["ocr_text"])
        joined = "\n".join(chunks)
        if len(joined) >= max_chars:
            return joined[:max_chars]
    return "\n".join(chunks)[:max_chars]
