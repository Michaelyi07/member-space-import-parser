# -*- coding: utf-8 -*-
"""虚构测试文件生成（单一事实源）。

tests/conftest.py 用这些构建器在 tmp 目录生成；scripts/make_fixtures.py 用同一
构建器在 fixtures/ 目录物化交付文件（≥6 个，工单口径）。全部为虚构数据，
不含任何真实个人信息或企业信息。
"""
from __future__ import annotations

import csv
import os

from openpyxl import Workbook


def make_csv_gb18030(path: str) -> None:
    """① GB18030 编码 CSV：中文姓名/部门，含前导零编号列。"""
    rows = [
        ["员工编号", "姓名", "部门", "入职日期"],
        ["0001", "张伟明", "会员运营部", "2023-03-05"],
        ["0002", "李慧珍", "招商部", "2023-07-18"],
        ["0003", "王志强", "客服部", "2024-01-10"],
    ]
    with open(path, "w", encoding="gb18030", newline="") as f:
        csv.writer(f).writerows(rows)


def make_csv_bom(path: str) -> None:
    """② 带 BOM 的 UTF-8 CSV：中文列名与值。"""
    rows = [
        ["企业编号", "企业名称", "联系人", "联系电话"],
        ["E0001", "星辰科技（虚构）", "陈丽", "021-6555-0001"],
        ["E0002", "云帆贸易（虚构）", "赵鹏", "021-6555-0002"],
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def make_csv_leading_zero(path: str) -> None:
    """⑥ 前导零编号列 CSV（AC4）。"""
    rows = [
        ["工位编号", "楼层", "状态"],
        ["003F-A01-07", "3", "available"],
        ["003F-A01-08", "3", "leased"],
        ["00042", "2", "reserved"],
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def make_xlsx_merged(path: str) -> None:
    """③ 合并单元格 xlsx：区域列（A 列）跨行合并（AC2）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "工位表"
    ws.append(["区域", "工位编号", "状态"])
    ws.append(["华东区", "003F-A01-01", "available"])
    ws.append([None, "003F-A01-02", "leased"])       # 区域列在合并区内
    ws.append([None, "003F-A01-03", "reserved"])
    ws.merge_cells("A2:A4")                          # 左上角 A2="华东区"
    ws.append(["华南区", "005F-B01-01", "available"])
    ws.append([None, "005F-B01-02", "leased"])
    ws.merge_cells("A5:A6")
    wb.save(path)


def make_xlsx_two_title_rows(path: str) -> None:
    """④ 表头上方 2 行标题（AC3：第 3 行为表头）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "会员企业"
    ws["A1"] = "2024 年度会员企业名册（虚构）"
    ws["A2"] = "导出时间：2024-06-30　制表人：数据组（虚构）"
    ws["A3"] = "企业名称"
    ws["B3"] = "统一社会信用代码（虚构）"
    ws["C3"] = "会员等级"
    ws["A4"] = "星辰科技（虚构）"
    ws["B4"] = "91310000MA1K00000X"
    ws["C4"] = "A"
    ws["A5"] = "云帆贸易（虚构）"
    ws["B5"] = "91310000MA1K00001W"
    ws["C5"] = "B"
    wb.save(path)


def make_xlsx_multisheet(path: str) -> None:
    """⑤ 多 sheet：sheet1 空备注页 + sheet2 首个非空数据页 + sheet3。"""
    wb = Workbook()
    ws0 = wb.active
    ws0.title = "说明"
    ws0["A1"] = "本页无数据表"
    ws1 = wb.create_sheet("工位明细")
    ws1.append(["工位编号", "月租金（分）"])
    ws1.append(["003F-A01-01", "120000"])
    ws2 = wb.create_sheet("历史记录")
    ws2.append(["月份", "退租数"])
    ws2.append(["2024-01", 2])
    wb.save(path)


def make_xlsx_dates(path: str) -> None:
    """补充：日期单元格（序列号 + 格式化文本双保留）。"""
    import datetime
    wb = Workbook()
    ws = wb.active
    ws.title = "签约"
    ws.append(["企业名称", "签约日期"])
    ws.append(["星辰科技（虚构）", datetime.datetime(2024, 3, 15)])
    ws.append(["云帆贸易（虚构）", datetime.datetime(2024, 5, 20, 14, 30, 0)])
    wb.save(path)


def make_csv_many_rows(path: str, n_rows: int) -> None:
    """超行数上限（AC5：TOO_MANY_ROWS），n_rows 按测试配置注入。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["编号", "名称"])
        for i in range(n_rows):
            w.writerow([f"{i:06d}", f"虚构行{i}"])


def make_txt(path: str) -> None:
    """UNSUPPORTED_FORMAT 样本。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write("这不是表格文件")


ALL_BUILDERS = {
    "members_gb18030.csv": make_csv_gb18030,
    "companies_utf8bom.csv": make_csv_bom,
    "workstations_leading_zero.csv": make_csv_leading_zero,
    "workstations_merged.xlsx": make_xlsx_merged,
    "members_two_title_rows.xlsx": make_xlsx_two_title_rows,
    "multisheet.xlsx": make_xlsx_multisheet,
    "contracts_dates.xlsx": make_xlsx_dates,
    "toomanyrows.csv": None,  # 行数按需生成
    "not_a_table.txt": make_txt,
}


def materialize_all(out_dir: str, many_rows: int = 50001) -> list[str]:
    """物化全部交付样本到 out_dir，返回文件名清单（供 make_fixtures.py）。"""
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for name, builder in ALL_BUILDERS.items():
        p = os.path.join(out_dir, name)
        if builder is None:
            make_csv_many_rows(p, many_rows)
        else:
            builder(p)
        made.append(name)
    return made
