"""docagent (集約 JSON のデータ操作 API) のエントリポイント。

スキル内に同梱された docagent パッケージを sys.path に追加して CLI を起動する。
カレントディレクトリに依存せず、どこから実行しても動く。初回は共有仮想環境
(プロジェクトルート直下の .venv) を uv で用意し、その python で実行し直す。
使い方: python run_docagent.py <サブコマンド> [オプション]
"""

import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parent
sys.path.insert(0, str(_scripts))

from _bootstrap import ensure_env

ensure_env(Path(__file__), _scripts / "requirements.txt")

from docagent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
