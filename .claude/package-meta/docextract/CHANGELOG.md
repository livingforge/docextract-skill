# Changelog — docextract

## Unreleased

Monosashi 評価 (`agents-20260702T164626Z`) のフィードバック反映。信頼性・観測性・
再現性・ガバナンス・ハーネスの底上げ（後方互換、公開 API・出力スキーマは非破壊）。

### Added
- 構造化イベントログ `docextract/obs.py`（JSON Lines）。1 実行を相関 ID (`run_id`)
  で貫き、`docextract → docagent` に環境変数 `DOCEXTRACT_RUN_ID` / `--run-id` で伝播。
  監査ログだけから 1 run を再構成できる。
- 評価ハーネス `scripts/eval/`（`run_eval.py` + `cases.jsonl`）。合否基準を data として
  宣言し列挙実行する、視点分離の評価ランナー。
- カバレッジ設計 `docs/coverage.md`（視点別カバレッジ + 未評価サーフェスの明示列挙）。
- 脅威モデル `package-meta/docextract/threat-model.md`（脅威 → 防御層 → 検証テストの対応表）。
- ハッシュ固定ロックファイル `requirements.lock`。`_bootstrap` が優先して決定論的に
  インストールする。OCR モデルの明示ピン用 env（`DOCEXTRACT_OCR_VERSION` /
  `DOCEXTRACT_OCR_DET_MODEL` / `DOCEXTRACT_OCR_REC_MODEL`）。
- GOVERNANCE に解決可能なオーナー連絡先と定期棚卸しスケジュールを明文化。

### Changed
- PDF 画像抽出の `bare except: return`（silent degradation）を廃止。劣化を握り潰さず
  `result.json` の `degraded` に構造化記録し、監査ログに相関 ID 付きで残す（observable）。

## 0.1.0 (2026-07-02)

初回リリース。

- Office 文書 (docx / xlsx / xlsm / pptx) と PDF からテキスト・表・画像を抽出し
  JSON 形式で出力する CLI / Python API
- 画像内テキストの OCR (`ocr_text`)。バックエンドは RapidOCR (Apache-2.0、既定) と
  Windows 標準 OCR (winocr 経由) の 2 系統、`auto` でフォールバック
- 画像として貼られた表の検出と構造復元 (rapid_layout + rapid_table / SLANet-plus)。
  行・列を復元し通常の `table` 要素として出力
- Word のテキストボックス内テキストの抽出 (`style: "textbox"`)
- PDF 解析は pdfplumber (MIT) + pypdf (BSD-3-Clause)。全依存を商用利用可能な
  OSS (MIT / BSD / Apache-2.0) で構成
- 単体テスト (18 件) をバンドルに同梱 (`scripts/tests/`)。フィクスチャは
  実行時生成でネットワーク・OCR モデル不要、配布先で自己検証できる
