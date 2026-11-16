# -*- coding: utf-8 -*-
"""AC2：合并单元格展开——合并区域覆盖的每一行都得到左上角的值。"""
from import_parser.parser import parse_file


def test_merged_region_expanded_every_row(fx, cfg):
    r = parse_file(fx.merged, "workstations_merged.xlsx", cfg)
    assert r.headers == ["区域", "工位编号", "状态"]
    # A2:A4 合并（华东区覆盖数据行 0-2），A5:A6 合并（华南区覆盖数据行 3-4）
    assert [row["区域"] for row in r.rows] == ["华东区", "华东区", "华东区", "华南区", "华南区"]
    assert [row["工位编号"] for row in r.rows] == [
        "003F-A01-01", "003F-A01-02", "003F-A01-03", "005F-B01-01", "005F-B01-02"]
    assert r.sheet_used == "工位表"


def test_merged_anchor_empty_yields_blank(fx, tmp_path, cfg):
    """左上角为空的合并区域：覆盖单元格展开为空串（不臆造值）。"""
    from openpyxl import Workbook
    p = str(tmp_path / "empty_anchor.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["备注", "编号"])
    ws.append([None, "X1"])
    ws.append([None, "X2"])
    ws.merge_cells("A2:A3")  # 左上角 A2 空
    wb.save(p)
    r = parse_file(p, "empty_anchor.xlsx", cfg)
    assert [row["备注"] for row in r.rows] == ["", ""]
