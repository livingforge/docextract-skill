# -*- coding: utf-8 -*-
"""標準パック — 継承チェーンの解決と文書カタログ（Phase 1）

設計は .specdb/docs/standard-pack-design.md。ここで実装するのは:
  - metamodel.yaml の `extends` から継承チェーン（単一親）を解決する
  - パックの templates/ を多層テンプレート検索・std/ プレフィックス参照に供する
  - パックの文書カタログとプロジェクト文書の from_standard マージ
  - テンプレート上書きの可視化（STD-W301 / STD-W303）

メタモデルのマージ・L1/L2 準拠検証・pack.lock は Phase 2 以降。
engine はパックの存在を知らない（「メタモデルの出所」非依存の原則）。
このモジュールを使うのは generate.py 等の上位ツールだけ。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from engine import Problem

TOOL_DIR = Path(__file__).resolve().parent

# extends の「パック名@major.minor」形式。これ以外はパス直接参照（開発モード）
_SPEC_RE = re.compile(r"[a-z0-9-]+@\d+\.\d+")


@dataclass
class Pack:
    """解決済みのパック 1 層。meta は pack.yaml の内容そのまま。"""
    name: str
    version: str
    dir: Path
    meta: dict = field(default_factory=dict)

    @property
    def templates_dir(self) -> Path:
        return self.dir / self.meta.get("templates", "templates")

    @property
    def documents_dir(self) -> Path:
        return self.dir / self.meta.get("documents", "documents")


def read_extends(root: Path) -> str | None:
    """metamodel.yaml の extends 宣言（無ければ None）。engine はこのキーを無視する。"""
    mm_file = root / "metamodel.yaml"
    if not mm_file.is_file():
        return None
    with open(mm_file, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("extends")


def resolve_chain(root: Path, problems: list[Problem]) -> list[Pack]:
    """継承チェーンを近い層から順に解決して返す（[事業部, 全社] の順）。

    extends が無ければ空リスト（スタンドアロン。従来動作そのまま）。
    解決失敗・バージョン不一致・循環は error を積み、解決できた層までを返す。
    """
    spec = read_extends(root)
    packs: list[Pack] = []
    seen: set[str] = set()
    base = root                       # パス形式 extends の相対基準（宣言した層）
    while spec:
        pack = _resolve_one(str(spec).strip(), root, base, problems)
        if pack is None:
            break
        if pack.name in seen:
            problems.append(Problem("error", f"pack:{pack.name}",
                                    "STD-E003 継承チェーンが循環している"))
            break
        seen.add(pack.name)
        packs.append(pack)
        spec, base = pack.meta.get("extends"), pack.dir
    return packs


def _resolve_one(spec: str, project_root: Path, base: Path,
                 problems: list[Problem]) -> Pack | None:
    """extends 1 段分を解決する。spec は 'name@major.minor' かパス。"""
    if not _SPEC_RE.fullmatch(spec):
        # パス直接参照（開発モード）。宣言した層のディレクトリからの相対
        return _load_pack((base / spec).resolve(), None, spec, problems)
    name, ver = spec.split("@")
    want = tuple(ver.split("."))
    candidates = [project_root / "packs" / name]          # vendored
    for p in os.environ.get("SPECDB_PACK_PATH", "").split(os.pathsep):
        if p:
            candidates.append(Path(p) / name)             # 追加検索パス
    candidates.append(TOOL_DIR / "packs" / name)          # ツール/スキル同梱
    for d in candidates:
        if (d / "pack.yaml").is_file():
            return _load_pack(d, want, spec, problems)
    problems.append(Problem("error", f"pack:{name}",
                            "STD-E001 パックを解決できない（探索: "
                            + ", ".join(str(c) for c in candidates) + "）"))
    return None


def _load_pack(d: Path, want: tuple | None, spec: str,
               problems: list[Problem]) -> Pack | None:
    f = d / "pack.yaml"
    if not f.is_file():
        problems.append(Problem("error", f"pack:{spec}",
                                f"STD-E001 pack.yaml が無い: {d}"))
        return None
    with open(f, encoding="utf-8") as fh:
        meta = yaml.safe_load(fh) or {}
    name, version = meta.get("pack"), str(meta.get("version") or "")
    if not name or not version:
        problems.append(Problem("error", f"pack:{spec}",
                                f"STD-E001 pack.yaml に pack / version が無い: {f}"))
        return None
    if want is not None and tuple(version.split(".")[:2]) != want:
        problems.append(Problem("error", f"pack:{name}",
                                f"STD-E002 extends '{spec}' と解決されたパックの "
                                f"version '{version}' が不一致"))
        return None
    return Pack(name, version, d, meta)


# ---------- テンプレートの多層検索 ----------

def template_search_dirs(root: Path, packs: list[Pack]) -> list[Path]:
    """テンプレート検索パス: プロジェクト → 近い層のパック → …（近い者勝ち）。"""
    return [root / "templates", *(p.templates_dir for p in packs)]


def prefix_map(packs: list[Pack]) -> dict[str, Path]:
    """親層版を明示参照するプレフィックス: std/（直近層）・std2/（その親）…。

    同名テンプレートを部分上書きする際の {% extends "std/…" %} が使う。
    """
    return {("std" if i == 0 else f"std{i + 1}"): p.templates_dir
            for i, p in enumerate(packs)}


def check_template_overrides(root: Path, packs: list[Pack],
                             problems: list[Problem]) -> None:
    """プロジェクト層によるパックテンプレートの上書きを可視化する。

    - `_` 始まり（ハウススタイル部品）の上書き = STD-W301（様式逸脱）
    - {% extends "std/…" %} を使わない同名全置換 = STD-W303（fork によるドリフト）
    パック層どうしの上書きは統制下のカスタマイズなので対象外（設計メモ §6.3）。
    """
    tdir = root / "templates"
    if not tdir.is_dir() or not packs:
        return
    pack_names = {f.name for p in packs if p.templates_dir.is_dir()
                  for f in p.templates_dir.glob("*.j2")}
    for f in sorted(tdir.glob("*.j2")):
        if f.name not in pack_names:
            continue
        if f.name.startswith("_"):
            problems.append(Problem("warn", f"templates/{f.name}",
                                    "STD-W301 ハウススタイル部品をプロジェクト層で"
                                    "上書きしている（様式逸脱）"))
        elif not re.search(r"""{%-?\s*extends\s+["']std""", f.read_text(encoding="utf-8")):
            problems.append(Problem("warn", f"templates/{f.name}",
                                    "STD-W303 標準テンプレートの全置換"
                                    "（{% extends \"std/…\" %} + block 上書きを推奨）"))


# ---------- 文書カタログと from_standard マージ ----------

def document_catalog(packs: list[Pack]) -> dict[str, tuple[dict, Pack]]:
    """チェーン全層の文書カタログ {名前: (定義, パック)}。近い層が優先。"""
    catalog: dict[str, tuple[dict, Pack]] = {}
    for pack in reversed(packs):      # ルート層から重ね、近い層で上書き
        if not pack.documents_dir.is_dir():
            continue
        for f in sorted(pack.documents_dir.glob("*.yaml")):
            with open(f, encoding="utf-8") as fh:
                catalog[f.stem] = (yaml.safe_load(fh) or {}, pack)
    return catalog


class _KeepMissing(dict):
    """format_map 用: 未定義の {名前} は展開せずそのまま残す。"""
    def __missing__(self, key):
        return "{" + key + "}"


def _dig(d: dict, path: str):
    """'preface.purpose' のようなドット区切りで入れ子の値を引く。"""
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def merge_document(doc: dict, catalog: dict[str, tuple[dict, Pack]],
                   problems: list[Problem], where: str) -> dict | None:
    """プロジェクト文書定義の from_standard を標準カタログとマージする。

    from_standard が無ければそのまま返す。error を積んだら None
    （その文書は生成対象から外れ、error なので生成自体も止まる）。
    カタログ側の title / output に書いた {パラメータ名} はマージ後の
    トップレベル値で展開される（例: 基本設計書_{system_name}.html）。
    """
    name = doc.get("from_standard")
    if not name:
        return doc
    if name not in catalog:
        problems.append(Problem("error", where,
                                f"from_standard '{name}' が標準文書カタログに無い"
                                f"（候補: {', '.join(sorted(catalog)) or 'なし'}）"))
        return None
    base = dict(catalog[name][0])
    params = base.pop("params", None) or {}
    doc_no_spec = base.pop("doc_no", None)
    base.pop("abstract", None)
    merged = {**base, **{k: v for k, v in doc.items() if k != "from_standard"}}
    ok = True
    for p in params.get("required") or []:
        if _dig(merged, p) in (None, ""):
            problems.append(Problem("error", where,
                                    f"STD-E202 必須パラメータ '{p}' が未指定"))
            ok = False
    # doc_no: カタログ側が {pattern: …} なら採番規則として検査、素の値なら既定値
    if isinstance(doc_no_spec, dict) and doc_no_spec.get("pattern"):
        got = merged.get("doc_no")
        if got is not None and not re.fullmatch(doc_no_spec["pattern"], str(got)):
            problems.append(Problem("error", where,
                                    f"STD-E203 doc_no '{got}' が採番規則 "
                                    f"'{doc_no_spec['pattern']}' に不一致"))
            ok = False
    elif doc_no_spec is not None:
        merged.setdefault("doc_no", doc_no_spec)
    if not ok:
        return None
    ctx = _KeepMissing((k, v) for k, v in merged.items()
                       if isinstance(v, (str, int, float)))
    return {k: (v.format_map(ctx) if isinstance(v, str) else v)
            for k, v in merged.items()}


def collect_documents(root: Path, packs: list[Pack],
                      problems: list[Problem]) -> list[tuple[str, dict]]:
    """生成対象の文書定義を (名前, マージ済み定義) で列挙する。

    = プロジェクト documents/（from_standard はカタログとマージ）
      + プロジェクトが実体化していない非 abstract の標準文書。
    abstract: true の標準文書は実体化されない限り生成対象に入らない（§6.4）。
    """
    catalog = document_catalog(packs)
    docs: list[tuple[str, dict]] = []
    project_stems: set[str] = set()
    docs_dir = root / "documents"
    if docs_dir.is_dir():
        for f in sorted(docs_dir.glob("*.yaml")):
            with open(f, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
            project_stems.add(f.stem)
            merged = merge_document(doc, catalog, problems, f"documents/{f.stem}")
            if merged is not None:
                docs.append((f.stem, merged))
    for stem, (doc, _pack) in sorted(catalog.items()):
        if stem not in project_stems and not doc.get("abstract"):
            docs.append((stem, dict(doc)))
    return sorted(docs, key=lambda d: d[0])
