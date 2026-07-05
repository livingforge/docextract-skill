# -*- coding: utf-8 -*-
"""specdb ツール群の統一エントリポイント — ディレクトリごと実行する

    python <specdbツールのディレクトリ> <サブコマンド> [オプション...]

例（プロジェクトルートで）:
    python specdb engine                      # 検証レポート + 統計
    python .claude/skills/specdb engine       # スキル展開先でも同じ形式
    python .github/skills/specdb sync-check   # プラットフォームはパス先頭だけの差

サブコマンドは同じディレクトリの各ツール *.py にそのまま委譲するので、
従来の `python <dir>/engine.py ...` 形式も引き続き使える。
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# サブコマンド -> (ツールファイル, 一行説明)。usage の表示順を兼ねる。
COMMANDS: dict[str, tuple[str, str]] = {
    "engine": ("engine.py", "検証レポート + 統計（error で exit 1）"),
    "generate": ("generate.py", "設計書を out/ に生成"),
    "diff": ("diff.py", "ベースライン差分"),
    "history": ("history.py", "変更履歴（Git から意味的に再構成）"),
    "visualize": ("visualize.py", "対話型グラフビューア out/specdb.html"),
    "sync-check": ("sync_check.py", "実装と正本の乖離を検出"),
    "mutate": ("mutate.py", "アイテム/関係の追加・変更・承認"),
}
ALIASES = {"validate": "engine", "sync_check": "sync-check"}


def _usage(stream) -> None:
    print(f"使い方: python {HERE.name} <サブコマンド> [オプション...]", file=stream)
    print("サブコマンド:", file=stream)
    for name, (_, desc) in COMMANDS.items():
        print(f"  {name:<11} {desc}", file=stream)
    print("各サブコマンドの詳細: python "
          f"{HERE.name} <サブコマンド> --help", file=stream)


def main(argv: list[str]) -> int:
    if not argv:
        _usage(sys.stderr)
        return 2
    if argv[0] in ("-h", "--help"):
        _usage(sys.stdout)
        return 0
    cmd = ALIASES.get(argv[0], argv[0])
    if cmd not in COMMANDS:
        print(f"不明なサブコマンド: {argv[0]}", file=sys.stderr)
        _usage(sys.stderr)
        return 2
    script = HERE / COMMANDS[cmd][0]
    # ツール同士の import（sync_check -> engine 等）を場所に依らず成立させる
    sys.path.insert(0, str(HERE))
    sys.argv = [str(script)] + argv[1:]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
