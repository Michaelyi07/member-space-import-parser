# -*- coding: utf-8 -*-
"""AC1：GB18030 与带 BOM 的 UTF-8 CSV 解析后中文无乱码。"""
import csv

from import_parser.parser import parse_file

MEMBERS_HEADERS = ["员工编号", "姓名", "部门", "入职日期"]


def test_gb18030_chinese_intact(fx, cfg):
    r = parse_file(fx.gb18030, "members_gb18030.csv", cfg)
    assert r.encoding == "gb18030"
    assert r.headers == MEMBERS_HEADERS
    assert r.rows[0]["姓名"] == "张伟明"
    assert r.rows[1]["部门"] == "招商部"
    assert all("�" not in v for row in r.rows for v in row.values())


def test_bom_detected_and_stripped(fx, cfg):
    r = parse_file(fx.bom, "companies_utf8bom.csv", cfg)
    assert r.encoding == "utf-8-sig"
    assert r.headers[0] == "企业编号"  # 无 \ufeff 前缀
    assert r.rows[0]["企业名称"] == "星辰科技（虚构）"


def test_plain_utf8_recorded(fx, cfg):
    r = parse_file(fx.leading_zero, "workstations_leading_zero.csv", cfg)
    assert r.encoding == "utf-8"


def test_gb18030_superset_gbk_bytes(fx, tmp_path, cfg):
    """GBK 字节流（GB18030 超集）也应正确解码。"""
    import codecs
    p = str(tmp_path / "gbk.csv")
    rows = [["名称", "备注"], ["云帆贸易（虚构）", "续约成功"]]
    with open(p, "w", encoding="gbk", newline="") as f:
        csv.writer(f).writerows(rows)
    r = parse_file(p, "gbk.csv", cfg)
    assert r.encoding == "gb18030"
    assert r.rows[0]["备注"] == "续约成功"
