"""register_extractor() — 抽出器レジストリ（拡張ポイント）を検証する。

新形式のエクステンダを本体を書き換えずに追加・差し替えできること、および
不正な登録が拒否されることを end-to-end で確認する。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import docextract
from docextract import (
    available_extractors,
    extract,
    register_extractor,
)
from docextract.models import ExtractionResult, TextElement


@pytest.fixture
def restore_registry():
    """テストごとにレジストリ（_EXTRACTORS / SUPPORTED_EXTENSIONS）を復元する。"""
    saved = dict(docextract._EXTRACTORS)
    saved_supported = docextract.SUPPORTED_EXTENSIONS
    try:
        yield
    finally:
        docextract._EXTRACTORS.clear()
        docextract._EXTRACTORS.update(saved)
        docextract.SUPPORTED_EXTENSIONS = saved_supported


def _fake_extractor(input_path: Path, saver) -> ExtractionResult:
    """組み込み抽出器と同じ契約のダミー抽出器。"""
    text = Path(input_path).read_text(encoding="utf-8")
    return ExtractionResult(
        source=str(input_path),
        file_type="fake",
        elements=[TextElement(content=text)],
    )


def test_register_new_format_is_dispatched(tmp_path, restore_registry):
    register_extractor(".fake", _fake_extractor)
    assert ".fake" in available_extractors()
    assert ".fake" in docextract.SUPPORTED_EXTENSIONS

    src = tmp_path / "note.fake"
    src.write_text("こんにちは", encoding="utf-8")
    data = extract(src, output_dir=tmp_path / "out")
    assert data["file_type"] == "fake"
    assert data["elements"][0]["content"] == "こんにちは"


def test_extension_is_case_insensitive(tmp_path, restore_registry):
    register_extractor(".FAKE", _fake_extractor)
    src = tmp_path / "n.fake"  # 大文字で登録しても小文字入力にディスパッチ
    src.write_text("x", encoding="utf-8")
    assert extract(src, output_dir=tmp_path / "out")["file_type"] == "fake"


def test_register_requires_leading_dot(restore_registry):
    with pytest.raises(ValueError):
        register_extractor("fake", _fake_extractor)


def test_register_requires_callable(restore_registry):
    with pytest.raises(TypeError):
        register_extractor(".fake", "not-callable")


def test_existing_format_not_overwritten_without_flag(restore_registry):
    with pytest.raises(ValueError):
        register_extractor(".docx", _fake_extractor)


def test_overwrite_existing_format_when_forced(tmp_path, restore_registry):
    register_extractor(".docx", _fake_extractor, overwrite=True)
    src = tmp_path / "r.docx"
    src.write_text("差し替え済み", encoding="utf-8")
    # 差し替えた抽出器が使われる（本物の docx パーサではなくテキストとして読む）
    data = extract(src, output_dir=tmp_path / "out")
    assert data["file_type"] == "fake"
    assert data["elements"][0]["content"] == "差し替え済み"


def test_available_extractors_returns_copy(restore_registry):
    snapshot = available_extractors()
    snapshot[".zzz"] = _fake_extractor  # コピーなので本体に影響しない
    assert ".zzz" not in docextract._EXTRACTORS
