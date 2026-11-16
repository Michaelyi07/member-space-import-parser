# -*- coding: utf-8 -*-
"""解析编排：格式分发 → 编码/工作簿读取 → 表头识别 → 行结构化 → 限额校验。"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field

from .config import ImportConfig
from .encoding import decode_csv
from .errors import ImportErrorCode, ImportValidationError
from .excel import Cell, read_excel_any

SUPPORTED_SUFFIXES = (".xlsx", ".xls", ".csv")


@dataclass
class SheetInfo:
    name: str
    non_empty_rows: int


@dataclass
class ParseResult:
    file_sha256: str
    suffix: str
    encoding: str | None = None          # 仅 CSV：utf-8-sig / utf-8 / gb18030
    sheets: list[SheetInfo] = field(default_factory=list)
    sheet_used: str | None = None
    header_row_index: int | None = None  # 所用 sheet 内 0-based
    skipped_title_rows: int = 0
    headers: list[str] = field(default_factory=list)
    alias_hits: int = 0
    rows: list[dict[str, str]] = field(default_factory=list)
    """import_row.raw_payload：键=原始表头文本，值=字符串。"""
    date_serials: dict[int, dict[str, float]] = field(default_factory=dict)
    """row_index(0-based) → {表头: Excel 原始序列号}（仅日期单元格，双保留口径）。"""
    blank_rows_skipped: int = 0
    blank_rows_in_data: int = 0
    """数据区（表头之后）内的空白行数（同 skipped 口径，供映射器对账行号）。"""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_file(path: str, original_name: str, cfg: ImportConfig) -> str:
    """后缀 + 大小校验（工单错误码口径）。返回小写后缀。"""
    dot = original_name.rfind(".")
    suffix = original_name[dot:].lower() if dot >= 0 else ""
    if suffix not in SUPPORTED_SUFFIXES:
        raise ImportValidationError(
            ImportErrorCode.UNSUPPORTED_FORMAT,
            f"仅支持 {', '.join(SUPPORTED_SUFFIXES)}，收到 {original_name!r}")
    import os
    size = os.path.getsize(path)
    if size > cfg.max_file_bytes:
        raise ImportValidationError(
            ImportErrorCode.FILE_TOO_LARGE,
            f"文件 {size} 字节 > 上限 {cfg.max_file_bytes}（IMPORT_MAX_FILE_MB="
            f"{cfg.max_file_mb}）")
    if size == 0:
        raise ImportValidationError(ImportErrorCode.EMPTY_FILE, "0 字节文件")
    return suffix


def read_csv_rows(path: str) -> tuple[list[list[str]], str]:
    with open(path, "rb") as f:
        raw = f.read()
    text, enc = decode_csv(raw)
    rows = list(csv.reader(io.StringIO(text)))
    return rows, enc


def _grid_to_str_rows(grid_rows: list[list[Cell]]) -> list[list[str]]:
    return [[c.text for c in row] for row in grid_rows]


def parse_file(path: str, original_name: str, cfg: ImportConfig,
               aliases: dict[str, list[str]] | None = None,
               sheet_name: str | None = None) -> ParseResult:
    """入口：落盘后的文件 → ParseResult。

    sheet_name=None 时用第一个非空 sheet（工单口径），同时返回全部 sheet 清单
    供前端选择；指定 sheet_name 不存在 → SHEET_NOT_FOUND；全部 sheet 为空 → NO_SHEET_DATA。
    """
    suffix = validate_file(path, original_name, cfg)
    sha = _sha256_file(path)

    encoding: str | None = None
    if suffix == ".csv":
        str_rows, encoding = read_csv_rows(path)
        sheet_rows = {"csv": [[Cell(text=t) for t in row] for row in str_rows]}
    else:
        grids = read_excel_any(path, suffix)
        sheet_rows = {name: grid.rows for name, grid in grids.items()}
        if not sheet_rows:
            raise ImportValidationError(ImportErrorCode.NO_SHEET_DATA,
                                        "工作簿不含任何工作表")

    sheets = [SheetInfo(name=n, non_empty_rows=sum(
        1 for r in rs if any(c.text.strip() for c in r)))
        for n, rs in sheet_rows.items()]
    used = sheet_name or next((s.name for s in sheets if s.non_empty_rows > 0), None)
    if used is None:
        raise ImportValidationError(ImportErrorCode.NO_SHEET_DATA,
                                    "所有工作表均为空")
    if sheet_name and used not in sheet_rows:
        raise ImportValidationError(ImportErrorCode.SHEET_NOT_FOUND,
                                    f"sheet {sheet_name!r} 不存在；可选："
                                    f"{[s.name for s in sheets]}")

    grid_rows = sheet_rows[used]
    from .header import detect_header
    det = detect_header(grid_rows, aliases)

    # 数据区行 → raw_payload；空白行跳过计数；行数限额在物化时硬校验
    rows: list[dict[str, str]] = []
    date_serials: dict[int, dict[str, float]] = {}
    blank_in_data = 0
    headers = _dedupe_headers(det.headers)
    n_cols = len(headers)
    for ri in range(det.header_row_index + 1, len(grid_rows)):
        cells = grid_rows[ri]
        # P0-1（审查修复）：先按表头列数截断，杜绝截断行越界
        texts = [c.text.strip() for c in cells[:n_cols]]
        if not any(texts):
            blank_in_data += 1
            continue
        if len(rows) >= cfg.max_rows:
            raise ImportValidationError(
                ImportErrorCode.TOO_MANY_ROWS,
                f"数据行超过上限 {cfg.max_rows}（IMPORT_MAX_ROWS）")
        # 截断行（比表头短）右侧缺失列不补键，由映射器决定必填校验口径
        payload = {headers[ci]: texts[ci] for ci in range(len(texts))}
        serials = ({headers[ci]: cells[ci].serial
                    for ci in range(min(len(cells), n_cols))
                    if cells[ci].serial is not None}
                   if suffix != ".csv" else {})
        if serials:
            date_serials[len(rows)] = serials
        rows.append(payload)

    blank_above = sum(1 for r in grid_rows[:det.header_row_index]
                      if not any(c.text.strip() for c in r))

    return ParseResult(
        file_sha256=sha, suffix=suffix, encoding=encoding, sheets=sheets,
        sheet_used=used, header_row_index=det.header_row_index,
        skipped_title_rows=det.skipped_title_rows, headers=headers,
        alias_hits=det.alias_hits, rows=rows, date_serials=date_serials,
        blank_rows_skipped=blank_above + blank_in_data,
        blank_rows_in_data=blank_in_data,
    )


def _dedupe_headers(headers: list[str]) -> list[str]:
    """P1-3（审查修复）：重复/空表头去重（追加 _2/_3…），防 payload 键覆盖静默丢列。

    合并展开后的表头常见同名多列；键覆盖是静默数据丢失，故去重并保留顺序。
    口径记录在 result.headers（去重后），README 已写明。
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for h in headers:
        name = h
        if name == "":
            name = "_空列"
        n = seen.get(name, 0)
        if n:
            seen[name] = n + 1
            name = f"{name}_{n + 1}"
        else:
            seen[name] = 1
        out.append(name)
    return out
