# -*- coding: utf-8 -*-
"""错误码（工单口径）：超限/格式/编码失败均有稳定码，调用方按码分支。"""
from __future__ import annotations


class ImportErrorCode:
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_ROWS = "TOO_MANY_ROWS"
    EMPTY_FILE = "EMPTY_FILE"
    NO_SHEET_DATA = "NO_SHEET_DATA"
    SHEET_NOT_FOUND = "SHEET_NOT_FOUND"
    HEADER_NOT_FOUND = "HEADER_NOT_FOUND"
    DECODE_FAILED = "DECODE_FAILED"


class ImportValidationError(Exception):
    """携带稳定错误码的校验失败；detail 供日志与接口 422 体。"""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)
