"""docextract — Office 文書 (docx/xlsx/pptx) と PDF から
テキスト・表・画像を抽出して JSON 形式で出力するライブラリ。

使い方 (Python API):
    from docextract import extract
    result = extract("report.docx")                 # 既定 .docextract/output/ へ
    result = extract("report.docx", output_dir="out")  # 明示指定も可

使い方 (CLI):
    python -m docextract report.docx slides.pptx
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import identity, manifest, paths
from .extractors import extract_docx, extract_pdf, extract_pptx, extract_xlsx
from .extractors.base import ImageSaver
from .image_tables import detect_tables
from .models import ExtractionResult, ImageElement, TableElement
from .ocr import ocr_image

__version__ = "0.1.0"

_EXTRACTORS = {
    ".docx": extract_docx,
    ".xlsx": extract_xlsx,
    ".xlsm": extract_xlsx,
    ".pptx": extract_pptx,
    ".pdf": extract_pdf,
}

SUPPORTED_EXTENSIONS = tuple(_EXTRACTORS)


def register_extractor(
    extension: str,
    extractor: Any,
    *,
    overwrite: bool = False,
) -> None:
    """新しい形式の抽出器を登録する（拡張ポイント／差し替え機構）。

    組み込みの ``_EXTRACTORS`` はハードコードだが、この関数で外部から形式を
    追加・差し替えできる。これにより新形式のエクステンダを、本体を書き換えずに
    足せる（登録レジストリによる依存性注入）。

    引数:
        extension: ``.foo`` のような**先頭ドット付き**の拡張子（大小無視）。
        extractor: ``(input_path: Path, saver: ImageSaver) -> ExtractionResult``
            のシグネチャを持つ callable。組み込み抽出器と同じ契約。
        overwrite: 既存の形式（``.pdf`` 等）を差し替えたいときだけ True。
            既定では既存形式への上書きを ``ValueError`` で拒否する。

    ``SUPPORTED_EXTENSIONS`` は登録に追従して更新される。
    """
    ext = extension.lower()
    if not ext.startswith(".") or len(ext) < 2:
        raise ValueError(f"拡張子は先頭ドット付きで指定してください: {extension!r}")
    if not callable(extractor):
        raise TypeError("extractor は呼び出し可能である必要があります")
    if ext in _EXTRACTORS and not overwrite:
        raise ValueError(
            f"形式 {ext} は既に登録済みです（差し替えるには overwrite=True）"
        )
    _EXTRACTORS[ext] = extractor
    global SUPPORTED_EXTENSIONS
    SUPPORTED_EXTENSIONS = tuple(_EXTRACTORS)


def available_extractors() -> dict[str, Any]:
    """登録済みの ``{拡張子: 抽出器}`` のコピーを返す（差し替え状況の確認用）。"""
    return dict(_EXTRACTORS)


def extract(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    save_json: bool = True,
    ocr: bool = True,
    ocr_lang: str = "ja",
    ocr_backend: str = "auto",
    image_tables: bool = True,
    record_manifest: bool = True,
    run_id: str | None = None,
) -> dict[str, Any]:
    """1 つの文書を解析し、抽出結果を dict で返す。

    出力先は入力パスから決まる**衝突しない ID** (:mod:`identity`) のフォルダ:
    画像は ``<output_dir>/<id>/images/`` に保存され、``save_json=True`` なら
    ``<output_dir>/<id>/result.json`` も書き出す。ID は正規化済み絶対パスの
    ハッシュを含むため、別フォルダの同名ファイルでも衝突しない。``output_dir``
    省略時は ``.docextract/output`` (環境変数 ``DOCEXTRACT_HOME`` で基点変更可)。

    ``ocr=True`` の場合、抽出した各画像に対して OCR を実行し、
    画像内のテキストを ``ocr_text`` として付加する
    (スクリーンショットや図として貼られたテキスト・表への対応)。

    ``image_tables=True`` の場合、各画像に対して表検出
    (rapid_layout + rapid_table) を実行し、見つかった表を
    通常の ``table`` 要素として追加する。location には
    ``from_image`` (元画像) と ``bbox_in_image`` が入る。

    ``record_manifest=True`` かつ ``save_json=True`` なら、出力先直下の
    ``index.json`` (抽出マニフェスト) にこの文書を ID で登録する。

    ``run_id`` を渡すと、その値をマニフェストの各エントリに ``run_id`` として
    記録する。バッチや複数エージェント連携で一連の処理を横断追跡するための
    相関 ID（CLI が 1 実行につき 1 つ発番して各文書へ引き回す）。
    """
    input_path = Path(input_path)
    if output_dir is None:
        output_dir = paths.output_dir()
    if not input_path.is_file():
        raise FileNotFoundError(f"ファイルが見つかりません: {input_path}")

    ext = input_path.suffix.lower()
    extractor = _EXTRACTORS.get(ext)
    if extractor is None:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise ValueError(f"未対応の形式です: {ext} (対応形式: {supported})")

    # 出力フォルダ名は identity で作る衝突しない ID。別フォルダの同名ファイルでも
    # パスが違えば ID が異なるため上書き事故が起きない。
    source_key = identity.canonical_source(input_path)
    doc_id = identity.doc_id(input_path, source_key=source_key)
    doc_out_dir = Path(output_dir) / doc_id
    doc_out_dir.mkdir(parents=True, exist_ok=True)

    saver = ImageSaver(doc_out_dir)
    result: ExtractionResult = extractor(input_path, saver)

    images = [el for el in result.elements if isinstance(el, ImageElement)]
    for el in images:
        image_path = doc_out_dir / el.file
        if ocr:
            el.ocr_text = ocr_image(image_path, lang=ocr_lang, backend=ocr_backend)
        if image_tables:
            for rows, bbox in detect_tables(image_path, lang=ocr_lang):
                location = dict(el.location)
                location["from_image"] = el.file
                if bbox:
                    location["bbox_in_image"] = bbox
                result.elements.append(TableElement(rows=rows, location=location))

    # 抽出後に同一性情報を付与する (抽出器は本文の抽出だけに集中させる)。
    result.id = doc_id
    result.source_abspath = source_key
    result.source_hash = identity.source_hash(source_key)
    result.content_hash = identity.content_hash(input_path)

    data = result.to_dict()

    if save_json:
        json_path = doc_out_dir / "result.json"
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if record_manifest:
            manifest.record(
                {
                    "id": doc_id,
                    "source": str(input_path),
                    "source_abspath": source_key,
                    "source_hash": result.source_hash,
                    "content_hash": result.content_hash,
                    "file_type": result.file_type,
                    "result_path": (doc_out_dir / "result.json").as_posix(),
                    "size": input_path.stat().st_size,
                    "run_id": run_id,
                },
                path=Path(output_dir) / "index.json",
            )
    return data
