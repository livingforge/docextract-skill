# 依存ライブラリとライセンス — docextract

本体 (docextract) のライセンスは MIT ([LICENSE](LICENSE))。
実行時依存はすべて商用利用可能なライセンスで構成している。

## 実行時依存 (pip)

| ライブラリ | 用途 | ライセンス |
|-----------|------|-----------|
| python-docx | Word (.docx) 解析 | MIT |
| openpyxl | Excel (.xlsx/.xlsm) 解析 | MIT |
| python-pptx | PowerPoint (.pptx) 解析 | MIT |
| pdfplumber (pdfminer.six) | PDF テキスト・表 | MIT |
| pypdf | PDF 画像抽出 | BSD-3-Clause |
| rapidocr | OCR エンジン (ONNX Runtime) | Apache-2.0 |
| rapid-layout | 画像内レイアウト解析 (表領域検出) | Apache-2.0 |
| rapid-table | 表構造復元 (SLANet-plus) | Apache-2.0 |
| Pillow | 画像処理 | MIT-CMU |
| winocr (任意) | Windows 標準 OCR のラッパー | MIT (エンジンは OS 機能) |

## バージョン固定と再現性 (lockfile)

- `requirements.txt` は floor-pin (`>=`) で許容範囲を示す**宣言**。
- `requirements.lock` は `uv pip compile --generate-hashes` で生成した**ハッシュ固定の
  ロックファイル**。全依存 (推移的依存を含む) を `==` と `--hash` で固定し、
  改竄検知つきの決定論的インストールを可能にする。
- 起動スクリプト (`_bootstrap.ensure_env`) は、`requirements.lock` があればそれを
  優先してインストールする (無ければ `requirements.txt` にフォールバック)。
- 更新手順: `requirements.txt` を編集 → `uv pip compile requirements.txt
  --generate-hashes -o requirements.lock` を再実行 → 差分をレビューしてコミット。

## 学習済みモデル (初回実行時に自動ダウンロード)

| モデル | 配布元 | ライセンス |
|--------|--------|-----------|
| PP-OCR 系 検出・認識モデル (日本語ほか) | RapidAI (PaddleOCR 由来) | Apache-2.0 |
| pp_layout_cdla (レイアウト解析) | RapidAI | Apache-2.0 |
| slanet-plus (表構造認識) | RapidAI (PaddleOCR 由来) | Apache-2.0 |

- モデルは共有仮想環境 (プロジェクトルート直下の `.venv`) の site-packages 配下に
  キャッシュされる (起動スクリプトが uv で自動構築する環境)。

### モデルのバージョン固定 (再現性)

- RapidOCR の既定モデルは、インストール済み `rapidocr` に同梱の
  `default_models.yaml` が**モデル URL・バージョンタグ・SHA256 ダイジェスト**で
  固定している。よって `requirements.lock` で `rapidocr==<版>` を固定すれば、
  使われるモデルのダイジェストも**推移的に固定**される (自動 DL の版ドリフトを排除)。
- さらに明示ピン / 完全オフライン運用のための環境変数:

  | 環境変数 | 効果 |
  |---|---|
  | `DOCEXTRACT_OCR_VERSION` | 使う OCR バージョン (例 `PP-OCRv4`) を det/rec 双方に固定 |
  | `DOCEXTRACT_OCR_DET_MODEL` | 検出モデルのローカル `.onnx` パスを指定 (自動 DL を回避) |
  | `DOCEXTRACT_OCR_REC_MODEL` | 認識モデルのローカル `.onnx` パスを指定 (自動 DL を回避) |

- 完全オフライン運用では、ネットワークのある環境で一度モデルをキャッシュし、その
  パスを上記 env で固定するか、`--ocr-backend windows` + `--no-image-tables` で
  外部モデル取得を完全に回避する。

## 意図的に採用しなかったもの

| 候補 | 理由 |
|------|------|
| PyMuPDF | AGPL-3.0 のため商用組み込みに制約 (0.1.0 で pdfplumber + pypdf に置換済み) |
| Tesseract | 外部バイナリのインストールが必要で配布が重い |
| EasyOCR / PaddleOCR 本体 | PyTorch / PaddlePaddle 依存が大きい (数 GB) |
