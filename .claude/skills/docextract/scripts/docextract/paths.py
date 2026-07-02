"""出力先ディレクトリの解決を一元管理するモジュール。

docextract の抽出結果 (``output/``) と docagent の集約ストア (``store/``) は、
既定でプロジェクト直下の**単一ディレクトリ** ``.docextract/`` 配下にまとめる。
ホストプロジェクトが既に持つ ``output`` / ``store`` と衝突しないよう、
ドット始まりの固有名を1つだけ作る方針 (``.pytest_cache`` 等と同じ発想)。

    .docextract/
      output/            <- docextract の抽出結果 (<名前>_<拡張子>/result.json)
      store/
        library.json     <- docagent の集約 JSON
        categories.json  <- 利用者が編集できるタクソノミー

配置換えは環境変数 ``DOCEXTRACT_HOME`` で行う (docextract / docagent 共通の
唯一のつまみ)。個別の上書きは docextract の ``--output-dir`` /
docagent の ``--store`` でも従来どおり可能。

env は呼び出しごとに読む (import 時に固定しない) ので、テストや呼び出し側が
``DOCEXTRACT_HOME`` を設定すれば即座に反映される。
"""

from __future__ import annotations

import os
from pathlib import Path

# データ基点を差し替える環境変数と、その既定値。
ENV_HOME = "DOCEXTRACT_HOME"
DEFAULT_HOME = ".docextract"


def home_dir() -> Path:
    """データ基点ディレクトリ (env ``DOCEXTRACT_HOME``、既定 ``.docextract``)。"""
    return Path(os.environ.get(ENV_HOME) or DEFAULT_HOME)


def output_dir() -> Path:
    """docextract の抽出結果ルート (``<home>/output``)。"""
    return home_dir() / "output"


def store_dir() -> Path:
    """docagent の集約ストア用ディレクトリ (``<home>/store``)。"""
    return home_dir() / "store"


def store_path() -> Path:
    """集約 JSON ファイル (``<home>/store/library.json``)。"""
    return store_dir() / "library.json"


def categories_path() -> Path:
    """タクソノミー定義ファイル (``<home>/store/categories.json``)。"""
    return store_dir() / "categories.json"
