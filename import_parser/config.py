# -*- coding: utf-8 -*-
"""环境变量配置（工单口径：配置与密钥只从环境变量读取）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
        if v <= 0:
            raise ValueError
        return v
    except ValueError as e:
        raise ValueError(f"环境变量 {name}={raw!r} 必须为正整数") from e


@dataclass(frozen=True)
class ImportConfig:
    """IMPORT_MAX_FILE_MB / IMPORT_MAX_ROWS / IMPORT_STORAGE_DIR。

    默认值即工单口径：20 MB、50000 行；storage_dir 无默认——落盘是本服务职责，
    未配置即 fail-fast（测试显式注入 tmp 目录）。
    """
    max_file_mb: int = field(default_factory=lambda: _env_int("IMPORT_MAX_FILE_MB", 20))
    max_rows: int = field(default_factory=lambda: _env_int("IMPORT_MAX_ROWS", 50000))
    storage_dir: str = field(default_factory=lambda: os.environ.get("IMPORT_STORAGE_DIR", ""))

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024

    @classmethod
    def for_test(cls, storage_dir: str, max_file_mb: int = 20, max_rows: int = 50000) -> "ImportConfig":
        """测试显式注入，绕过环境变量（避免测试互相污染）。"""
        return cls(max_file_mb=max_file_mb, max_rows=max_rows, storage_dir=storage_dir)
