# -*- coding: utf-8 -*-
"""docsummary スキルの統一エントリポイント — ディレクトリごと実行する

    python <スキルディレクトリ> run   <doc_id...> [オプション]  # 文書を要約
    python <スキルディレクトリ> list                            # 要約状態の一覧
    python <スキルディレクトリ> show  <doc_id>                  # 要約 Markdown を表示
    python <スキルディレクトリ> config --check | --init         # 接続設定

サブコマンド (run/list/show/config) は docsummary パッケージ自身の CLI が解釈する。
ここでは実体のランチャー run_docsummary.py へそのまま委譲する。
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv: list[str]) -> int:
    script = HERE / "run_docsummary.py"
    sys.path.insert(0, str(HERE))
    sys.argv = [str(script), *argv]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
