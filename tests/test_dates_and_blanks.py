# -*- coding: utf-8 -*-
"""日期单元格双保留 + 空白行计数。"""
import datetime

from import_parser.parser import parse_file


def test_date_cell_serial_and_text(fx, cfg):
    r = parse_file(fx.dates, "contracts_dates.xlsx", cfg)
    assert r.headers == ["企业名称", "签约日期"]
    row0 = r.rows[0]
    assert row0["签约日期"] == "2024-03-15"          # 格式化文本
    assert r.date_serials[0]["签约日期"] == 45366.0   # Excel 原始序列号（2024-03-15）
    # datetime 单元格：格式化文本含时间部分
    assert r.rows[1]["签约日期"] == "2024-05-20 14:30:00"
    assert r.date_serials[1]["签约日期"] > 45366.0


def test_date_serial_openpyxl_reference(fx, cfg):
    """序列号与 openpyxl 官方换算一致（防自造轮子漂移）。"""
    from openpyxl.utils.datetime import to_excel
    r = parse_file(fx.dates, "contracts_dates.xlsx", cfg)
    assert r.date_serials[0]["签约日期"] == to_excel(datetime.datetime(2024, 3, 15))


def test_blank_rows_counted(fx, tmp_path, cfg):
    """完全空白的行跳过并计数（表头上方 + 数据区）。"""
    from openpyxl import Workbook
    p = str(tmp_path / "blanks.xlsx")
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "名册标题（虚构）"          # 标题行（非空，计入 skipped_title_rows）
    ws["A2"] = None                        # 空白行
    ws["A3"] = "编号"
    ws["B3"] = "名称"
    ws["A4"] = "001"
    ws["B4"] = "甲（虚构）"
    ws["A5"] = None                        # 数据区空白行
    ws["B5"] = None
    ws["A6"] = "002"
    ws["B6"] = "乙（虚构）"
    wb.save(p)
    r = parse_file(p, "blanks.xlsx", cfg)
    assert r.header_row_index == 2
    assert len(r.rows) == 2
    assert r.blank_rows_in_data == 1
    assert r.blank_rows_skipped == 2       # 表头上方空白 1 + 数据区空白 1
