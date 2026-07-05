---
name: spec-sync
description: Sync implementation changes into .specdb, the project's spec-as-data single source of truth - map a git diff (or the work just done in this session) onto spec items and relations, register additions/changes with status review, pass machine validation (error 0), regenerate the views, and report what awaits review. Use after implementing/changing/removing a feature, or when asked to "specdb を更新 / 仕様データに反映 / 設計データを同期 / spec-sync". Part of this project's Definition of Done (CLAUDE.md).
---

# spec-sync — 実装差分を .specdb（設計データの正本）へ同期する

このプロジェクトの設計データの正本は `.specdb/`（items/ + relations/、YAML）である。
実装だけ進んで正本が古くなるのを防ぐため、機能の追加・変更・廃止のあとに
この手順で `.specdb` を更新する。CLAUDE.md の「完了の定義」の一部。

前提:

- 正本は `.specdb/items/` と `.specdb/relations/`。`out/` は生成ビュー（直接編集しない）
- 使える語彙（種別・属性・関係）は `.specdb/metamodel.yaml` の宣言がすべて
- specdb ツール一式は `.github/skills/specdb/scripts/`（`--root` 省略時は自動で `./.specdb` を使う）

## 手順

### 1. 差分の把握

同期対象の実装変更を洗い出す。

- この会話で実装した内容が第一の入力（何を作った・変えた・消したか）
- 補助として `git status` / `git diff`（未コミット分）、コミット済みなら該当コミットの diff

### 2. 影響判定 — 実装の変化を specdb の語彙に写像する

| 実装の変化 | .specdb での操作 |
| --- | --- |
| スキル / エージェント / モジュールの新設 | `skill` / `agent` / `module` アイテム追加 + `realizes` `uses` `produces` 等の関係 |
| 利用者から見える機能の追加 | `function` アイテム追加（`func_id` は既存 F-xx の次番）+ 実現主体から `realizes` |
| 既存機能の振る舞い変更・拡張 | 該当アイテムの `description` 等を更新し `status: review` に戻す |
| 生成物・入出力ファイルの追加 | `artifact` 追加 + `produces` / `consumes` |
| 対応文書形式の追加 | `file-format` 追加 + `supports` |
| 依存ライブラリの追加 | `library` 追加 + `depends-on` |
| 新しい設計上の約束・規律 | `design-rule` 追加 + 従う構成要素に `follows`（`rules:` 埋め込み） |
| 機能・構成要素の廃止 | `status: deprecated` に変更（アイテムは削除しない） |

**仕様に影響しない変更**（タイポ修正・リファクタ・テストのみ・コメント等）なら、
`.specdb` は触らず「仕様影響なし」とその理由を報告して終了してよい。

### 3. 正本の更新

- 既存の `items/<種別>/core.yaml` の末尾に、既存項目と同じ粒度・文体（日本語・である調）で追記する
- `id` は種別の接頭辞に従う（`fn-` `sk-` `ag-` `mod-` `ar-` `fmt-` `dr-` `lib-`）。既存ファイルで確認する
- **新規・変更したアイテム/関係は `status: review` にする。** approved に上げるのは
  人がレビューした後（指示があったとき）だけ。自分で approved にしない
- `source`（出典）を必ず書く: `doc`（README・SKILL.md・実装ファイル等の実在パス）+
  `location`（section 等）+ `evidence`（根拠の原文）
- 関係は `relations/*.yaml` の該当ファイル（realizes / dataflow / uses / supports）へ追記する

### 4. 機械検証（ゲート）

```bash
python .github/skills/specdb/scripts/engine.py     # 検証 + 集計。error があれば exit 1
```

error 0 になるまで修正してから先へ進む（未定義参照・必須属性欠落・多重度違反・孤児が主な原因）。

### 5. ビュー再生成

```bash
python .github/skills/specdb/scripts/visualize.py  # .specdb/out/specdb.html（対話型グラフ）
python .github/skills/specdb/scripts/generate.py   # .specdb/documents/ に定義された設計書
```

### 6. 報告

- 追加・変更したアイテム / 関係の一覧（ID と要旨）
- `status: review` で登録した件数。ビューア（specdb.html）の「レビュー中」ボタンで
  レビュー対象とその隣接だけの関係グラフを確認できることを添える
- 仕様影響なしと判断した場合は、その判断根拠

## レビューの運用（参考）

レビュー担当が `out/specdb.html` の「レビュー中」表示で対象を確認し、承認されたら
該当アイテム / 関係の `status` を `approved` へ更新 → 再検証 → ビュー再生成する。
