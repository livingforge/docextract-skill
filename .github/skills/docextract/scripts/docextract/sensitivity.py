"""秘密度ラベル (Microsoft Purview / AIP) と暗号化・IRM 保護の検知。

このモジュールは 2 つの独立した関心事を扱う:

1. :func:`detect_protection` — ファイルが**暗号化 / IRM(RMS) 保護**されているかを
   判定する。保護文書は復号しない限り中身を読めず、COM 変換も認証待ちや権限
   エラーで不定に失敗する。抽出前にこれを検知し、「Office が無い」等と**取り違え
   ない明確なエラー**で fail-closed するために使う。

2. :func:`read_label` — **暗号化されていない**文書に付いた秘密度ラベル
   (``MSIP_Label_{GUID}_*`` プロパティ) を読み、成果物 (result.json / index.json)
   へ伝播するために使う。ラベルを機械可読な形で下流へ運び、機密文書が無印のまま
   コーパスへ流入するのを防ぐ。

いずれも**標準ライブラリのみ**で実装し、外部依存 (olefile 等) を増やさない
(ハッシュ固定の ``requirements.lock`` を汚さないため)。判定は保守的で、確証が
無ければ「保護なし / ラベルなし」を返す (誤検知で正常ファイルを止めない)。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Optional

# OLE2 複合ファイル (旧 Office 形式・および暗号化された OOXML) の先頭マジック。
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class ProtectedDocumentError(RuntimeError):
    """暗号化 / IRM(RMS) 保護された文書で、復号せずには抽出できないことを表す。

    「未対応形式」や「Office が無い」と取り違えないための専用型。メッセージには
    保護の種類 (IRM/RMS か パスワード暗号化か) と、権限を持つ利用者が復号済みの
    コピーを渡すべき旨を含める。
    """


def _u16(s: str) -> bytes:
    """OLE2 のディレクトリ内でストリーム名は UTF-16LE。マーカーを同形式に。"""
    return s.encode("utf-16-le")


# 暗号化 OOXML / 保護文書に現れる Office 暗号化 (MS-OFFCRYPTO) の構造名。
# これらは通常の (無保護の) 旧 Office 文書には現れないため、保護の指標になる。
_RMS_MARKERS = [
    _u16("DRMEncryptedTransform"),
    _u16("DRMEncryptedDataSpace"),
    _u16("DRMContent"),
    _u16("DRMViewerContent"),
    _u16("Microsoft.Metadata.DRMTransform"),
]
_ENC_MARKERS = [
    _u16("EncryptedPackage"),
    _u16("StrongEncryptionDataSpace"),
    _u16("StrongEncryptionTransform"),
    _u16("Microsoft.Container.EncryptionTransform"),
]
# 上のいずれかがあれば「Office 暗号化構造」を持つと判断する材料。
_DATASPACES_MARKER = _u16("DataSpaces")

# 検知のためのチャンク走査。ストリーム名を含むディレクトリはファイル末尾側にも
# 現れうるため全体を見るが、巨大ファイルでも一定メモリに収める。
_CHUNK = 1 << 20
# マーカー最大長ぶん重ねてチャンク境界での取りこぼしを防ぐ。
_OVERLAP = 64


def _scan_markers(path: Path, markers: list[bytes]) -> bool:
    with open(path, "rb") as f:
        prev = b""
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                return False
            window = prev + chunk
            if any(m in window for m in markers):
                return True
            prev = chunk[-_OVERLAP:]


def detect_protection(path: str | Path) -> Optional[dict[str, Any]]:
    """暗号化 / IRM 保護を検知する。保護なら情報 dict、無ければ ``None``。

    返す dict:
        ``kind`` : ``"irm"`` (IRM/RMS 保護 = 秘密度ラベルの暗号化) または
                   ``"encrypted"`` (パスワード等の暗号化)
        ``detail`` : 人間向けの短い説明

    判定は「OLE2 複合ファイルであり、かつ Office 暗号化構造 (DataSpaces /
    EncryptedPackage / DRM) を含む」ことに基づく。通常の OOXML は ZIP、通常の旧
    Office 文書は DataSpaces を持たないため、これらとは区別できる。
    """
    p = Path(path)
    try:
        with open(p, "rb") as f:
            head = f.read(len(_OLE_MAGIC))
    except OSError:
        return None
    # 暗号化 Office 文書は (旧形式も暗号化 OOXML も) OLE2 複合ファイル。
    # ZIP(=無保護 OOXML) やその他はここで対象外。
    if head != _OLE_MAGIC:
        return None
    if _scan_markers(p, _RMS_MARKERS):
        return {
            "kind": "irm",
            "detail": "IRM/RMS 保護 (秘密度ラベルによる暗号化) が施されています",
        }
    if _scan_markers(p, _ENC_MARKERS):
        return {
            "kind": "encrypted",
            "detail": "暗号化 (パスワード等) が施されています",
        }
    return None


# --- 秘密度ラベル (暗号化されていない文書のメタデータ) の読み取り --------------

# OOXML のカスタムプロパティ名前空間 (docProps/custom.xml)。ラベルはここに
# MSIP_Label_{GUID}_Name / _Enabled / _SetDate ... として格納される。
_CUSTOM_PART = "docProps/custom.xml"
_MSIP_PREFIX = "MSIP_Label_"


def read_label(path: str | Path) -> Optional[dict[str, Any]]:
    """秘密度ラベル (``MSIP_Label_*``) を読み、正規化した dict を返す。

    暗号化されていない OOXML (docx/xlsx/pptx、および旧形式を変換した OOXML) の
    ``docProps/custom.xml`` を読む。ラベルが無ければ ``None``。

    返す dict (存在する項目のみ):
        ``name`` ラベル表示名 / ``id`` ラベル GUID / ``enabled`` 有効か /
        ``set_date`` 付与日時 / ``site_id`` / ``method`` (Standard/Privileged) /
        ``content_bits``。複数ラベルが埋め込まれていれば ``all`` に全件を載せる。
    """
    p = Path(path)
    if not zipfile.is_zipfile(p):
        return None
    try:
        with zipfile.ZipFile(p) as z:
            if _CUSTOM_PART not in z.namelist():
                return None
            data = z.read(_CUSTOM_PART)
    except (zipfile.BadZipFile, KeyError, OSError):
        return None
    return _parse_msip_labels(data)


def _parse_msip_labels(data: bytes) -> Optional[dict[str, Any]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    # {guid: {field: value}} に畳む。名前空間は local 名で判定 (プレフィックス非依存)。
    grouped: dict[str, dict[str, str]] = {}
    for prop in root:
        name = prop.get("name") or ""
        if not name.startswith(_MSIP_PREFIX):
            continue
        guid, _, field = name[len(_MSIP_PREFIX) :].partition("_")
        value = "".join(prop.itertext()).strip()
        grouped.setdefault(guid, {})[field] = value

    if not grouped:
        return None

    labels = [_normalize_label(guid, fields) for guid, fields in grouped.items()]
    enabled = [l for l in labels if l.get("enabled")]
    primary = enabled[0] if enabled else labels[0]
    out = {k: v for k, v in primary.items() if v is not None}
    if len(labels) > 1:
        out["all"] = labels
    return out


def _normalize_label(guid: str, fields: dict[str, str]) -> dict[str, Any]:
    return {
        "id": guid or None,
        "name": fields.get("Name") or None,
        "enabled": (fields.get("Enabled", "").strip().lower() == "true"),
        "set_date": fields.get("SetDate") or None,
        "site_id": fields.get("SiteId") or None,
        "method": fields.get("Method") or None,
        "content_bits": fields.get("ContentBits") or None,
    }
