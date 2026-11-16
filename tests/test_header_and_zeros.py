# -*- coding: utf-8 -*-
"""AC3 + AC4：表头识别（2 行标题下方第 3 行为表头）与前导零保留。"""
from import_parser.parser import parse_file


def test_header_is_third_row(fx, cfg):
    r = parse_file(fx.two_titles, "members_two_title_rows.xlsx", cfg)
    # 1-based 第 3 行 = 0-based index 2
    assert r.header_row_index == 2
    assert r.skipped_title_rows == 2
    assert r.headers == ["企业名称", "统一社会信用代码（虚构）", "会员等级"]
    assert r.rows[0]["企业名称"] == "星辰科技（虚构）"
    assert len(r.rows) == 2


def test_alias_hits_win_over_cell_count(fx, tmp_path, cfg):
    """有别名配置时，别名命中多的行胜出（即使非空单元格数更少）。"""
    from openpyxl import Workbook
    p = str(tmp_path / "alias.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["杂项备注一", "杂项备注二", "杂项备注三", "杂项备注四"])   # 4 非空，0 命中
    ws.append(["member_name", "member_phone", None, None])              # 2 非空，2 命中
    ws.append(["云帆贸易（虚构）", "13800000000", None, None])
    wb.save(p)
    aliases = {"企业名称": ["member_name"], "联系电话": ["member_phone"]}
    r = parse_file(p, "alias.xlsx", cfg, aliases=aliases)
    assert r.header_row_index == 1
    assert r.alias_hits == 2
    assert r.rows[0]["member_name"] == "云帆贸易（虚构）"


def test_csv_leading_zeros_preserved(fx, cfg):
    r = parse_file(fx.leading_zero, "workstations_leading_zero.csv", cfg)
    assert [row["工位编号"] for row in r.rows] == ["003F-A01-07", "003F-A01-08", "00042"]
    assert r.rows[2]["工位编号"].startswith("000")


def test_xlsx_text_cell_leading_zeros_preserved(fx, tmp_path, cfg):
    """Excel 中以文本存储的编号列（前导零）解析后原样保留。"""
    from openpyxl import Workbook
    p = str(tmp_path / "lz.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["证件号（虚构）", "姓名"])
    ws["A2"] = "007"
    ws["A2"].number_format = "@"  # 文本格式
    ws["B2"] = "测试人（虚构）"
    ws["A3"] = "000123"
    ws["A3"].number_format = "@"
    ws["B3"] = "测试人二（虚构）"
    wb.save(p)
    r = parse_file(p, "lz.xlsx", cfg)
    assert [row["证件号（虚构）"] for row in r.rows] == ["007", "000123"]
