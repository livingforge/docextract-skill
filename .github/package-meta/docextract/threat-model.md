# 脅威モデル — docextract

想定する攻撃面・信頼境界と、各層の防御、そして**それを検証するテスト**を
対応づける文書。防御が単発の思いつきでなく、脅威に沿った多層防御であることを
機械検証可能な形で示す。関連: [GOVERNANCE.md](GOVERNANCE.md) /
`docs/coverage.md`（カバレッジ設計）。

## スコープと前提

- docextract は**ローカルの文書ファイルを解析するツール**であり、ネットワーク
  サービスとして公開されることは想定しない。
- 想定利用者は、自分（または自組織）が用意した資料フォルダを解析するエンジニア／
  エージェント。悪意ある第三者が任意入力を送り込む公開エンドポイントではない。
- したがって主眼は「**環境を壊す/汚す暗黙操作の抑止**」と「**壊れた/信頼できない
  データを黙って通さないこと**」であり、ネットワーク攻撃者対策ではない。

## 信頼境界（trust boundaries）

| # | 境界 | 内→外 / 外→内 | 主なリスク |
|---|---|---|---|
| B1 | ランチャー → OS / ネットワーク | 外向き（uv/依存の取得・インストール） | 暗黙のリモートコード実行・大容量DL・環境汚染 |
| B2 | 入力文書 → 抽出器 | 外→内（信頼できない可能性のあるファイル） | 破損/細工ファイルによる例外・部分的取りこぼし |
| B3 | docextract → docagent | 内→内（`result.json` の受け渡し） | 壊れた/欠損した中間成果物の伝播 |
| B4 | 設定・秘密情報 | 外→内（env / OCR 言語等） | 秘密のハードコード・ログ漏洩 |

## 脅威 → 防御層 → 検証テスト

| ID | 脅威 | 信頼境界 | 防御層 | 検証テスト |
|---|---|---|---|---|
| T1 | ランチャーがリモートインストーラを暗黙 download→exec、数百MB を無断DL、共有環境を汚染 | B1 | **D1**: opt-in + fail-closed の承認ゲート（`_bootstrap._gate`）。非対話・未承認は停止。`DOCEXTRACT_NO_UV_AUTOINSTALL` が最優先で禁止 | `tests/test_bootstrap_gate.py`（fail-closed / opt-in / 禁止フラグ優先 / 対話拒否） |
| T2 | standing override（`DOCEXTRACT_AUTOINSTALL=1` の常設）が per-run ゲートを恒久的に無効化 | B1 | **D1'**: 禁止フラグ `DOCEXTRACT_NO_UV_AUTOINSTALL` を opt-in より優先させ、CI/監査環境で常設 override を失効させる経路を用意 | `tests/test_bootstrap_gate.py::test_no_autoinstall_takes_precedence_over_optin` |
| T3 | 破損/細工された Office・PDF で抽出器が例外を投げ、処理全体が落ちる | B2 | **D2**: CLI は 1 ファイルの失敗を捕捉し `[NG]`＋非ゼロ終了で分離継続（他ファイルは処理） | `tests/test_cli.py`（未対応形式・存在しない・部分失敗） |
| T4 | 画像デコード等の劣化を黙って握り潰し、取りこぼしが silent degradation になる | B2 | **D3**: `bare except: return` を廃し、劣化を `result.degraded` に構造化記録＋監査ログに相関ID付きで残す（observable degradation） | `tests/test_pdf.py::test_image_extraction_records_degradation_not_silent`, `tests/test_obs.py` |
| T5 | 壊れた/欠損した `result.json`（`elements` 欠落・不正 JSON・生 Office 直渡し）が後工程へ伝播 | B3 | **D4**: docagent が境界でランタイム検証し hard-error で拒否（fail-closed な取り込み） | `tests/test_docagent.py`（invalid JSON / elements 欠落 / 生ファイル拒否） |
| T6 | 抽出器レジストリの差し替えで既存形式を無断上書き（意図しない挙動注入） | B3 | **D5**: `register_extractor` は既存形式の上書きを既定拒否（`overwrite=True` 明示が必要） | `tests/test_registry.py` |
| T7 | 秘密情報（トークン等）のハードコード / ログへの漏洩 | B4 | **D6**: 秘密はコードに持たず env 経由。監査ログは event/相関ID・件数など非機微メタのみを記録 | 設計レビュー（機微値をログイベントに載せない）／`dependencies.md` |

## 残存リスク（受容 / 今後）

- **入力ファジング未導入**: 破損ファイルの網羅的探索はしていない（代表ケースのみ）。
  巨大ファイルによる資源枯渇（DoS）は範囲外（`docs/coverage.md` の未評価サーフェス参照）。
- **モデル改竄**: OCR/表検出モデルは初回に自動 DL する。ダイジェスト固定は
  [dependencies.md](dependencies.md) の方針で段階導入中（`--ocr-backend windows` +
  `--no-image-tables` で外部モデルDLを完全回避できる）。
- **並行実行時の競合**: マニフェスト/ストアへの同時書き込みロックは未実装（単一プロセス前提）。

## 更新方針

- 新しい外部取得・新しい入力形式・新しい信頼境界を足したら、対応する脅威行と
  検証テストを本表に追加する。テストの無い防御は「主張」に留めない。
