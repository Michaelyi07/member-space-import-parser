# -*- coding: utf-8 -*-
"""CSV 解码链（工单口径）：依次尝试 UTF-8-BOM → UTF-8 → GB18030，记录识别结果。

实现细节：
- BOM 判定用字节前缀而非 utf-8-sig 兜底解码——utf-8-sig 对无 BOM 的 UTF-8 也能解成功，
  会把「无 BOM UTF-8」误记成 utf-8-sig；
- 三段全失败时按 GB18030 + errors="replace" 兜底并显式记录
  （GB18030 是 GBK/GB2312 的超集，替换解码不抛异常但可能有 �，warning 里写明）。
"""
from __future__ import annotations

import codecs

from .errors import ImportErrorCode, ImportValidationError

CSV_ENCODINGS = ("utf-8", "gb18030")
BOM_UTF8 = codecs.BOM_UTF8


def decode_csv(raw: bytes) -> tuple[str, str]:
    """返回 (text, encoding_record)。encoding_record 写入 import_batch.source_encoding。"""
    if not raw:
        raise ImportValidationError(ImportErrorCode.EMPTY_FILE, "CSV 文件为 0 字节")
    if raw.startswith(BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    for enc in CSV_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    text = raw.decode("gb18030", errors="replace")
    return text, "gb18030+replace"
