# -*- coding: utf-8 -*-
"""Excel 读取（xlsx 只读流式 / xls via xlrd）。

实测依据（openpyxl 3.1.5，2026-11-16）：
- ReadOnlyWorksheet 无 merged_cells 属性（AttributeError）——只读模式下合并单元格
  信息不可从 openpyxl API 获得；
- 因此 xlsx 的合并区域直接从 zip 内 xl/worksheets/sheetN.xml 的 <mergeCells> 解析
  （ElementTree，O(merge 数)），保持只读流式、内存有界，不二次加载工作簿；
- 日期单元格：openpyxl 把日期格式单元格转成 datetime —— 用
  openpyxl.utils.datetime.to_excel 反算原始序列号，与格式化文本一并保留
  （工单口径：序列号 + 格式化文本双保留）。

所有单元格输出为 Cell(text, serial?)：text 一律 str（前导零天然保留——
Excel 里以文本存储的编号列值就是字符串）。
"""
from __future__ import annotations

import datetime as _dt
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

from .errors import ImportErrorCode, ImportValidationError

try:
    import openpyxl
    from openpyxl import load_workbook
    from openpyxl.utils.datetime import to_excel as _to_excel
except ImportError as e:  # pragma: no cover
    raise ImportError("需要 openpyxl（requirements.txt）：pip install openpyxl") from e

try:
    import xlrd
except ImportError as e:  # pragma: no cover
    raise ImportError("需要 xlrd（requirements.txt）：pip install xlrd") from e


@dataclass
class Cell:
    text: str = ""
    """展示文本（前导零保留；日期=格式化文本；空单元格=""）。"""
    serial: float | None = None
    """Excel 原始日期序列号（仅日期/时间单元格有值；其余 None）。"""


@dataclass
class SheetGrid:
    name: str
    rows: list[list[Cell]] = field(default_factory=list)
    merged_ranges: int = 0


# ── xlsx ──────────────────────────────────────────────────────────────

_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
def _xlsx_merge_map(zf: zipfile.ZipFile) -> dict[str, list[tuple[int, int, int, int]]]:
    """sheet 名 → [(r1, r2, c1, c2) 0-based 闭区间]。

    从 xl/workbook.xml（名→rId）与 xl/_rels/workbook.xml.rels（rId→路径）定位
    sheet XML，再取 <mergeCells><mergeCell ref="A2:A4"/>。兼容绝对/相对 target。
    """
    wb_xml = ElementTree.fromstring(zf.read("xl/workbook.xml"))
    rels_xml = ElementTree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_target = {
        rel.get("Id"): rel.get("Target", "")
        for rel in rels_xml.iter("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
    }
    out: dict[str, list[tuple[int, int, int, int]]] = {}
    for sheet in wb_xml.iter(f"{_NS_MAIN}sheet"):
        name = sheet.get("name") or ""
        rid = sheet.get(f"{_NS_R}id") or ""
        target = rid_target.get(rid, "")
        if not target:
            continue
        # Target 兼容两种写法：相对（worksheets/sheet1.xml，相对 xl/）与
        # 绝对（/xl/worksheets/sheet1.xml，包根相对）——实测 openpyxl 产出后者
        t = target.lstrip("/")
        xml_path = t if t.startswith("xl/") else "xl/" + t
        parts = []
        for seg in xml_path.split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg not in ("", "."):
                parts.append(seg)
        xml_path = "/".join(parts)
        try:
            sheet_xml = ElementTree.fromstring(zf.read(xml_path))
        except KeyError:
            continue
        spans: list[tuple[int, int, int, int]] = []
        for mc in sheet_xml.iter(f"{_NS_MAIN}mergeCell"):
            ref = mc.get("ref") or ""
            m = re.match(r"([A-Z]+)(\d+):([A-Z]+)(\d+)$", ref)
            if not m:
                continue
            c1 = _col_to_index(m.group(1))
            c2 = _col_to_index(m.group(3))
            r1, r2 = int(m.group(2)) - 1, int(m.group(4)) - 1
            if r1 > r2 or c1 > c2:
                r1, r2, c1, c2 = min(r1, r2), max(r1, r2), min(c1, c2), max(c1, c2)
            spans.append((r1, r2, c1, c2))
        if spans:
            out[name] = spans
    return out


def _col_to_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _xlsx_cell_text(v) -> Cell:
    """values_only 单元格值 → Cell（日期双保留；数字规范化为文本）。"""
    if v is None:
        return Cell()
    if isinstance(v, _dt.datetime):
        try:
            serial = float(_to_excel(v))
        except Exception:
            serial = None
        # 纯日期（零点）输出日期文本；含时间的保留时间部分
        text = (v.strftime("%Y-%m-%d")
                if (v.hour == 0 and v.minute == 0 and v.second == 0
                    and getattr(v, "microsecond", 0) == 0)
                else v.strftime("%Y-%m-%d %H:%M:%S"))
        return Cell(text=text, serial=serial)
    if isinstance(v, _dt.date):
        try:
            serial = float(_to_excel(_dt.datetime(v.year, v.month, v.day)))
        except Exception:
            serial = None
        return Cell(text=v.strftime("%Y-%m-%d"), serial=serial)
    if isinstance(v, _dt.time):
        text = v.strftime("%H:%M:%S")
        serial = (v.hour * 3600 + v.minute * 60 + v.second) / 86400.0
        return Cell(text=text, serial=round(serial, 10))
    if isinstance(v, bool):
        return Cell(text="TRUE" if v else "FALSE")
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            return Cell(text=str(int(v)))
        # P1-8（审查修复）：%.15g 与 Excel 界面显示口径一致（15 位有效数字，
        # 规避 0.1+0.2 类二进制尾差如 0.30000000000000004）
        return Cell(text=format(v, ".15g"))
    return Cell(text=str(v))


def read_xlsx(path: str) -> dict[str, SheetGrid]:
    """只读流式读值 + zip 级合并区域解析 → {sheet 名: SheetGrid}。"""
    grids: dict[str, SheetGrid] = {}
    with zipfile.ZipFile(path) as zf:
        merge_map = _xlsx_merge_map(zf)
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            name = ws.title
            spans = merge_map.get(name, [])
            # P1-6（审查修复）：活跃区间法替代逐单元格全量扫描——
            # spans 按 r1 排序，指针推进激活新区域，过期（r2<ri）移除；
            # 复杂度 O(rows + spans)，50k 行大表不再分钟级
            pending = sorted(spans, key=lambda s: s[0])
            pend_i = 0
            active: list[tuple[int, int, int, int]] = []
            # 顶部锚点 → 值：流式中左上角单元格先于覆盖单元格出现，直接查表
            anchors: dict[tuple[int, int], Cell] = {}
            rows: list[list[Cell]] = []
            n_merged_total = len(spans)
            for ri, raw_row in enumerate(ws.iter_rows(values_only=True)):
                while pend_i < len(pending) and pending[pend_i][0] <= ri:
                    active.append(pending[pend_i])
                    pend_i += 1
                active = [sp for sp in active if sp[1] >= ri]
                out_row: list[Cell] = []
                for ci, v in enumerate(raw_row):
                    cell = _xlsx_cell_text(v)
                    if cell.text != "":
                        anchors[(ri, ci)] = cell
                    for (r1, r2, c1, c2) in active:
                        if c1 <= ci <= c2:  # r1 <= ri <= r2 已由 active 保证
                            if (ri, ci) != (r1, c1):
                                anchor = anchors.get((r1, c1), Cell())
                                # N1（复审建议）：覆盖格自身有值而锚为空时保留原值
                                # （非法重叠区域防御，Excel 正常文件不触发）
                                if cell.text == "" or anchor.text != "":
                                    cell = Cell(text=anchor.text, serial=anchor.serial)
                            break
                    out_row.append(cell)
                rows.append(out_row)
            grids[name] = SheetGrid(name=name, rows=rows, merged_ranges=n_merged_total)
    finally:
        wb.close()
    return grids


# ── xls ───────────────────────────────────────────────────────────────

def _xls_cell_text(cell) -> Cell:
    from xlrd import (
        XL_CELL_BOOLEAN, XL_CELL_DATE, XL_CELL_EMPTY, XL_CELL_NUMBER,
        XL_CELL_TEXT, xldate,
    )
    t = cell.ctype
    if t in (XL_CELL_EMPTY,):
        return Cell()
    if t == XL_CELL_TEXT:
        return Cell(text=str(cell.value))
    if t == XL_CELL_NUMBER:
        v = float(cell.value)
        if v.is_integer():
            return Cell(text=str(int(v)))
        return Cell(text=format(v, ".15g"))  # 与 Excel 显示口径一致（见 _xlsx_cell_text）
    if t == XL_CELL_DATE:
        serial = float(cell.value)
        try:
            dtv = xldate.xldate_as_datetime(serial, 0)
            text = dtv.strftime("%Y-%m-%d %H:%M:%S") if (dtv.hour or dtv.minute or dtv.second) \
                else dtv.strftime("%Y-%m-%d")
        except Exception:
            text = repr(serial)
        return Cell(text=text, serial=serial)
    if t == XL_CELL_BOOLEAN:
        return Cell(text="TRUE" if cell.value else "FALSE")
    return Cell(text=str(cell.value))


def read_xls(path: str) -> dict[str, SheetGrid]:
    """xlrd 只读解析；formatting_info=True 提供 merged_cells。活跃区间法同 read_xlsx。"""
    wb = xlrd.open_workbook(path, formatting_info=True)
    grids: dict[str, SheetGrid] = {}
    for sh in wb.sheets():
        spans = sorted(((r1, r2 - 1, c1, c2 - 1)
                        for (r1, r2, c1, c2) in sh.merged_cells), key=lambda s: s[0])
        pend_i, active = 0, []
        anchors: dict[tuple[int, int], Cell] = {}
        rows: list[list[Cell]] = []
        for ri in range(sh.nrows):
            while pend_i < len(spans) and spans[pend_i][0] == ri:
                active.append(spans[pend_i])
                pend_i += 1
            active = [sp for sp in active if sp[1] >= ri]
            out_row: list[Cell] = []
            for ci in range(sh.ncols):
                cell = _xls_cell_text(sh.cell(ri, ci))
                if cell.text != "":
                    anchors[(ri, ci)] = cell
                for (r1, r2, c1, c2) in active:
                    if c1 <= ci <= c2:
                        if (ri, ci) != (r1, c1):
                            anchor = anchors.get((r1, c1), Cell())
                            cell = Cell(text=anchor.text, serial=anchor.serial)
                        break
                out_row.append(cell)
            rows.append(out_row)
        grids[sh.name] = SheetGrid(name=sh.name, rows=rows, merged_ranges=len(spans))
    return grids


def read_excel_any(path: str, suffix: str) -> dict[str, SheetGrid]:
    if suffix == ".xlsx":
        return read_xlsx(path)
    if suffix == ".xls":
        return read_xls(path)
    raise ImportValidationError(ImportErrorCode.UNSUPPORTED_FORMAT, suffix)
