# Governance — docextract

このスキル／ライブラリのバージョニング・互換性・廃止（deprecation）方針。
変更履歴は [CHANGELOG.md](CHANGELOG.md)、依存とライセンスは [dependencies.md](dependencies.md) を参照。

## バージョニング（SemVer）

`docextract.__version__`（現在 `0.1.0`）は [Semantic Versioning 2.0.0](https://semver.org/) に従う。

- **MAJOR** — 後方非互換な変更（公開 API `extract()` のシグネチャ変更、出力 JSON スキーマの
  破壊的変更、対応形式の削除、CLI の既存フラグの意味変更）。
- **MINOR** — 後方互換な機能追加（新しい対応形式、`extract()` への任意引数の追加、
  新しい CLI フラグ、`register_extractor()` 等の拡張ポイント追加）。
- **PATCH** — 後方互換なバグ修正・抽出品質の改善・ドキュメント修正。

`0.y.z`（初期開発期）の間は MINOR で非互換が入りうる。`1.0.0` 以降は上記を厳格に守る。

## 公開 API と互換性の範囲

安定を保証する面（＝互換性ポリシーの対象）:

- Python: `docextract.extract()` と `SUPPORTED_EXTENSIONS`、拡張ポイント
  `register_extractor()` / `available_extractors()`。
- CLI: `run_docextract.py` / `run_docagent.py` のサブコマンドと既存フラグ。
- 出力: `result.json` の要素スキーマ（`docs/output-schema.md`）と `index.json` マニフェスト構造。

`_` 始まりのモジュール・関数（例: `_bootstrap`、内部ヘルパ）は**非公開**で、予告なく変わる。

## 廃止（Deprecation）方針

後方非互換にしたい要素は、**削除前に最低 1 つの MINOR リリースで非推奨**として残す:

1. 非推奨にする面は動作を維持したまま、CHANGELOG に `Deprecated` として明記し、
   Python 面では可能なら `DeprecationWarning` を出す。代替手段を必ず併記する。
2. 実際の削除は次の **MAJOR** で行う。
3. データ後方互換: `index.json` / `store/*.json` はスキーマに `version` を持つ。読み取り側は
   未知の新しいフィールドを無視し、古い `version` は読めるよう移行して扱う。

## サポートと報告

- 動作確認: バンドル同梱テスト（`docs/usage.md` の「自己検証」）で導入直後・依存更新後に検証できる。
- セキュリティ上の注意（リモートインストーラ実行・大容量ダウンロード）は承認ゲートで
  既定 opt-in・fail-closed に統制している（`SKILL.md` の Setup、`scripts/_bootstrap.py`）。
