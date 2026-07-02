"""共有仮想環境への自動ブートストラップ。

各スキルのランチャー (run_*.py) が、本体パッケージを import する前に
`ensure_env(...)` を呼ぶ。プロジェクトルート直下の共有 venv (``<root>/.venv``)
を uv で用意し、その venv の python で本体を実行し直す。

- 既に共有 venv の python で動いていれば何もしない (素通り)
- ``uv`` が無ければ公式インストーラで自動導入
  (``DOCEXTRACT_NO_UV_AUTOINSTALL=1`` で抑止し、手動導入を案内)
- venv が無ければ ``uv venv`` で作成 (必要なら Python 本体も uv が調達)
- スキルの requirements.txt が未反映なら ``uv pip install``
  (requirements のハッシュを marker に記録し、変化が無ければ再インストールしない)
- 共有 venv の python でスクリプトを実行し直し、その終了コードで終わる

共有 venv はルート直下に置くので、他スキルのランチャーからも
同じ ``_bootstrap`` を使って同一環境を共用できる (marker はスキルごとに分離)。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 再帰実行を防ぐガード。再 exec 後の子プロセスではこれが立っている。
_GUARD_ENV = "DOCEXTRACT_BOOTSTRAPPED"
# uv 自動インストールを抑止したいとき (CI やオフライン) に立てる。
_NO_AUTOINSTALL_ENV = "DOCEXTRACT_NO_UV_AUTOINSTALL"

_UV_INSTALL_HINT = (
    "  Windows      : powershell -ExecutionPolicy ByPass -c "
    '"irm https://astral.sh/uv/install.ps1 | iex"\n'
    "  macOS / Linux: curl -LsSf https://astral.sh/uv/install.sh | sh"
)


def _project_root(start: Path) -> Path:
    """スクリプトの位置からプロジェクトルートを推定する。

    配布物は ``<root>/.claude/skills/.../scripts/`` (または ``.github/...``) に
    展開されるので、``.claude`` / ``.github`` を祖先に見つけたらその親をルートと
    みなす。見つからなければ ``.git`` を辿り、最後は最上位を返す。
    """
    for parent in start.parents:
        if parent.name in (".claude", ".github"):
            return parent.parent
    for parent in start.parents:
        if (parent / ".git").exists():
            return parent
    return start.parents[-1]


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _find_uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    # PATH に無くても既定のインストール先にはあることが多い。
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv"),
        home / ".cargo" / "bin" / ("uv.exe" if os.name == "nt" else "uv"),
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


def _install_uv() -> str:
    if os.environ.get(_NO_AUTOINSTALL_ENV):
        sys.exit(
            "uv が見つかりません。インストールしてから再実行してください:\n"
            + _UV_INSTALL_HINT
        )
    print(
        "[bootstrap] uv が見つからないため公式インストーラで導入します "
        f"(抑止するには {_NO_AUTOINSTALL_ENV}=1)...",
        file=sys.stderr,
    )
    if os.name == "nt":
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "ByPass",
            "-c", "irm https://astral.sh/uv/install.ps1 | iex",
        ]
    else:
        cmd = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
    try:
        subprocess.run(cmd, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit(
            "uv の自動インストールに失敗しました。手動で導入してください:\n"
            + _UV_INSTALL_HINT
        )
    uv = _find_uv()
    if not uv:
        sys.exit(
            "uv を導入しましたが検出できませんでした。新しいシェルで再実行するか、"
            "手動で PATH を通してください。"
        )
    return uv


def _requirements_hash(requirements: Path) -> str:
    return hashlib.sha256(requirements.read_bytes()).hexdigest()


def ensure_env(script: Path, requirements: Path, skill: str = "docextract") -> None:
    """共有 venv を用意し、その python で ``script`` を実行し直す。

    引数:
        script:       呼び出し元ランチャーの ``__file__`` (Path)。
        requirements: このスキルの requirements.txt (Path)。
        skill:        marker 名の名前空間に使うスキル名。
    """
    script = script.resolve()
    venv = _project_root(script) / ".venv"
    venv_python = _venv_python(venv)

    # 既に共有 venv の python で動いていれば bootstrap 不要。
    try:
        if Path(sys.prefix).resolve() == venv.resolve():
            return
    except OSError:
        pass
    if os.environ.get(_GUARD_ENV):
        # 再 exec 済み。ループ防止のためここで打ち切る。
        return

    uv = _find_uv() or _install_uv()

    if not venv_python.exists():
        print(f"[bootstrap] 共有仮想環境を作成します: {venv}", file=sys.stderr)
        subprocess.run([uv, "venv", "--python", ">=3.10", str(venv)], check=True)

    # requirements が前回と同じなら再インストールしない。
    marker = venv / f".{skill}.reqhash"
    want = _requirements_hash(requirements)
    have = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    if have != want:
        print(
            f"[bootstrap] {skill} の依存を共有仮想環境へ導入します "
            "(初回は数百 MB のダウンロードが発生します)...",
            file=sys.stderr,
        )
        subprocess.run(
            [uv, "pip", "install", "--python", str(venv_python),
             "-r", str(requirements)],
            check=True,
        )
        marker.write_text(want, encoding="utf-8")

    # 共有 venv の python で本体を実行し直す。os.exec* は Windows で呼び出し元が
    # 完了を待たない挙動になるため、subprocess で待ち合わせて終了コードを引き継ぐ。
    env = dict(os.environ)
    env[_GUARD_ENV] = "1"
    completed = subprocess.run(
        [str(venv_python), str(script), *sys.argv[1:]], env=env
    )
    sys.exit(completed.returncode)
