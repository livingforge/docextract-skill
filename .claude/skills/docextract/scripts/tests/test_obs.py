"""obs.py — 構造化イベントログと run_id 相関・伝播を検証する。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docextract import obs
from docextract.models import ExtractionResult, ImageElement


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]


def test_run_id_shape():
    rid = obs.new_run_id()
    assert rid.startswith("run_")
    assert rid.count("_") >= 2  # run_<stamp>_<hex>


def test_resolve_run_id_prefers_explicit_over_env(monkeypatch):
    monkeypatch.setenv(obs.ENV_RUN_ID, "run_env")
    assert obs.resolve_run_id("run_explicit") == "run_explicit"


def test_resolve_run_id_falls_back_to_env(monkeypatch):
    monkeypatch.setenv(obs.ENV_RUN_ID, "run_env")
    assert obs.resolve_run_id(None) == "run_env"


def test_resolve_run_id_mints_when_absent(monkeypatch):
    monkeypatch.delenv(obs.ENV_RUN_ID, raising=False)
    assert obs.resolve_run_id(None).startswith("run_")


def test_events_are_json_lines_with_correlation(tmp_path, monkeypatch):
    monkeypatch.delenv(obs.ENV_RUN_ID, raising=False)
    run = obs.open_run("docextract", "run_fixed", base_dir=tmp_path)
    run.event("extract.start", doc_id="d1")
    run.warn("extract.degraded", doc_id="d1", reason="image_decode_failed")
    run.event("extract.done", doc_id="d1", degraded=1)

    log_path = tmp_path / "logs" / "run_fixed.jsonl"
    recs = _read_lines(log_path)
    assert [r["event"] for r in recs] == [
        "extract.start",
        "extract.degraded",
        "extract.done",
    ]
    # 全レコードが同じ run_id で相関し、component と ts を持つ
    assert {r["run_id"] for r in recs} == {"run_fixed"}
    assert all(r["component"] == "docextract" and r["ts"] for r in recs)
    assert recs[1]["level"] == "warning"


def test_child_shares_run_id_and_sink(tmp_path):
    run = obs.open_run("docextract.cli", "run_x", base_dir=tmp_path)
    child = run.child("docextract")
    child.event("extract.start", doc_id="d")
    recs = _read_lines(tmp_path / "logs" / "run_x.jsonl")
    assert recs[0]["run_id"] == "run_x"
    assert recs[0]["component"] == "docextract"


def test_env_run_id_propagates_when_not_explicit(tmp_path, monkeypatch):
    # 上流が採番した run_id を環境変数で引き継ぐ (docextract→docagent の伝播)
    monkeypatch.setenv(obs.ENV_RUN_ID, "run_upstream")
    run = obs.open_run("docagent.cli", None, base_dir=tmp_path)
    assert run.run_id == "run_upstream"


def test_degraded_marks_result_and_survives_serialization():
    res = ExtractionResult(source="s.pdf", file_type="pdf")
    res.elements.append(ImageElement("images/i.png", "png"))
    res.note_degraded("pdf.images", "image_decode_failed", page=2, image="i.jpg")
    out = res.to_dict()
    # 正常抽出した要素は残しつつ、劣化痕跡が観測可能な形で出力に載る
    assert out["summary"] == {"image": 1}
    assert out["degraded"]["count"] == 1
    assert out["degraded"]["items"][0] == {
        "stage": "pdf.images",
        "reason": "image_decode_failed",
        "page": 2,
        "image": "i.jpg",
    }


def test_no_degraded_key_when_clean():
    res = ExtractionResult(source="s.pdf", file_type="pdf")
    assert "degraded" not in res.to_dict()  # 正常時は既存出力を変えない
