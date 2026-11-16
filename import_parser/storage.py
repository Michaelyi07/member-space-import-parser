# -*- coding: utf-8 -*-
"""落盘：源文件存 IMPORT_STORAGE_DIR，以批次 id 命名（不用原文件名拼路径）。"""
from __future__ import annotations

import os

from .config import ImportConfig

SUPPORTED_SUFFIXES = (".xlsx", ".xls", ".csv")


def store_source(cfg: ImportConfig, batch_id: str,
                 original_name: str, content: bytes) -> tuple[str, int]:
    """写 {storage_dir}/{batch_id}{suffix}。返回 (stored_path, size)。

    后缀取自原文件名（格式判定依据），但路径不含原文件名——防注入/重名/非法字符。
    """
    dot = original_name.rfind(".")
    suffix = original_name[dot:].lower() if dot >= 0 else ""
    if suffix not in SUPPORTED_SUFFIXES:
        suffix = ""
    if not cfg.storage_dir:
        raise RuntimeError("IMPORT_STORAGE_DIR 未配置（fail-fast：落盘是本服务职责）")
    os.makedirs(cfg.storage_dir, exist_ok=True)
    dst = os.path.join(cfg.storage_dir, f"{batch_id}{suffix}")
    with open(dst, "wb") as f:
        f.write(content)
    size = os.path.getsize(dst)
    if size != len(content):
        raise IOError(f"落盘字节不一致：期望 {len(content)}，实际 {size}")
    return dst, size
