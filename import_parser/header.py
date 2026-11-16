# -*- coding: utf-8 -*-
"""表头行识别（工单口径）：在前 10 行中选「非空单元格最多、且与映射器列名别名
命中最多」的一行作为表头；表头上方的标题行丢弃并计数。

评分：alias_hits * 1000 + non_empty_count——别名命中是结构性证据，权重远大于
单元格数量；无别名配置（映射器工单未交付，接口桩）时退化为纯非空计数，
标题行（通常 1-2 个合并大标题单元格）天然输给表头行。

P1-5（审查修复）：别名与表头双方都做 NFKC 归一化后再比对——全角字母/全角
空格/全角括号等国内 Excel 常见混用不再漏配。
已知局限（P1-4）：无别名时纯非空计数在「数据行比表头行更满」的场景可能误选；
生产管线恒有映射器别名，README 已写明该局限与建议。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .errors import ImportErrorCode, ImportValidationError
from .excel import Cell

MAX_SCAN_ROWS = 10


def _norm(s: str) -> str:
    """NFKC 归一化 + 去全部空白：全角字母/全角空格（如"电 话"）与半角别名互通。"""
    n = unicodedata.normalize("NFKC", str(s))
    return "".join(ch for ch in n if not ch.isspace()).lower()


@dataclass
class HeaderDetection:
    headers: list[str]
    header_row_index: int
    skipped_title_rows: int
    alias_hits: int
    non_empty: int


def detect_header(rows: list[list[Cell]],
                  aliases: dict[str, list[str]] | None = None) -> HeaderDetection:
    alias_terms = {_norm(a) for lst in (aliases or {}).values() for a in lst if str(a).strip()}
    best_i, best_score, best_stats = None, -1, (0, 0)
    numeric_re = re.compile(r"^-?\d+(\.\d+)?$")
    for i, row in enumerate(rows[:MAX_SCAN_ROWS]):
        texts = [_norm(c.text) for c in row]
        non_empty = sum(1 for t in texts if t)
        if non_empty == 0:
            continue
        alias_hits = sum(1 for t in texts if t in alias_terms)
        # P1-4 缓解（审查修复）：数据行特征惩罚——纯数字单元格占比高的行更像数据。
        # 无别名时该启发式把「紧凑数据行比表头行更满」的误选挡掉
        # （实测用例：表头 1 非空格 vs 数据行 3 格曾被误选为表头）。
        numeric_count = sum(1 for t in texts if numeric_re.match(t))
        score = alias_hits * 1000 + non_empty - 2 * numeric_count
        if score > best_score:
            best_i, best_score, best_stats = i, score, (alias_hits, non_empty)
    if best_i is None:
        raise ImportValidationError(ImportErrorCode.HEADER_NOT_FOUND,
                                    "前 10 行内无任何非空行，无法识别表头")
    headers = [c.text.strip() for c in rows[best_i]]
    alias_hits, non_empty = best_stats
    return HeaderDetection(
        headers=headers,
        header_row_index=best_i,
        skipped_title_rows=best_i,
        alias_hits=alias_hits,
        non_empty=non_empty,
    )
