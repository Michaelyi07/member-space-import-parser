# -*- coding: utf-8 -*-
"""提交前专家审查（E185）修复项的回归守卫。

P0-1 截断行 / P0-2 serials 越界 / P1-1 真实 Session 落行 / P1-2 损坏文件闭环 /
P1-3 重复表头去重 / P1-5 全半角别名归一化 / P1-8 数值 %.15g。
"""
import hashlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from import_parser.config import ImportConfig
from import_parser.errors import ImportErrorCode, ImportValidationError
from import_parser.models import ImportBatch, ImportRow, Base
from import_parser.parser import parse_file
from import_parser.service import ImportService


def _cfg(tmp_path) -> ImportConfig:
    return ImportConfig.for_test(storage_dir=str(tmp_path / "storage"))


# ── P0-1：截断数据行不再 IndexError ─────────────────────────────────

def test_truncated_row_no_crash(fx, tmp_path):
    """CSV 尾部空列被省略（编号,姓名,电话 只写两列）→ 缺失列不补键，不崩。"""
    p = str(tmp_path / "trunc.csv")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("编号,姓名,电话\n0001,张三（虚构）\n0002,李四（虚构）,13800000000\n")
    r = parse_file(p, "trunc.csv", _cfg(tmp_path))
    assert r.rows[0] == {"编号": "0001", "姓名": "张三（虚构）"}  # 无"电话"键
    assert r.rows[1]["电话"] == "13800000000"


def test_xlsx_row_shorter_than_header(fx, tmp_path):
    from openpyxl import Workbook
    p = str(tmp_path / "short.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["甲列", "乙列", "丙列"])
    ws.append(["v1", "v2", "v3"])
    ws.append(["w1"])  # 截断行
    wb.save(p)
    r = parse_file(p, "short.xlsx", _cfg(tmp_path))
    # openpyxl 只读模式按 dimension 把截断行补齐到表头宽度（None→""）：
    # 与 CSV 的真实短行不同，xlsx 短行右侧是显式空串而非缺键
    assert r.rows[1] == {"甲列": "w1", "乙列": "", "丙列": ""}


# ── P1-3：重复/空表头去重，不静默丢列 ───────────────────────────────

def test_duplicate_headers_deduped(fx, tmp_path):
    from openpyxl import Workbook
    p = str(tmp_path / "dup.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "备注", "姓名"])
    ws.append(["甲（虚构）", "b1", "乙（虚构）"])
    wb.save(p)
    r = parse_file(p, "dup.xlsx", _cfg(tmp_path))
    assert r.headers == ["姓名", "备注", "姓名_2"]
    assert r.rows[0] == {"姓名": "甲（虚构）", "备注": "b1", "姓名_2": "乙（虚构）"}


def test_empty_headers_deduped(fx, tmp_path):
    from openpyxl import Workbook
    p = str(tmp_path / "emptyh.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["编号", None, None])
    ws.append(["001", "v1", "v2"])
    wb.save(p)
    r = parse_file(p, "emptyh.xlsx", _cfg(tmp_path))
    assert r.rows[0] == {"编号": "001", "_空列": "v1", "_空列_2": "v2"}


# ── P1-2：损坏/伪装文件闭环到 DECODE_FAILED ────────────────────────

def test_corrupt_xlsx_closes_batch(tmp_path):
    svc = ImportService(_cfg(tmp_path), __import__("import_parser.service", fromlist=["InMemorySession"]).InMemorySession())
    batch = svc.create_batch("org", "site", "fake.xlsx", b"this is not a zip")
    with pytest.raises(ImportValidationError) as e:
        svc.parse_batch(batch.id)
    assert e.value.code == ImportErrorCode.DECODE_FAILED
    assert batch.status == "parse_failed"
    assert batch.error_code == ImportErrorCode.DECODE_FAILED


def test_corrupt_xls_closes_batch(tmp_path):
    svc = ImportService(_cfg(tmp_path), __import__("import_parser.service", fromlist=["InMemorySession"]).InMemorySession())
    batch = svc.create_batch("org", "site", "fake.xls", b"\xd0\xcf garbage")
    with pytest.raises(ImportValidationError) as e:
        svc.parse_batch(batch.id)
    assert e.value.code == ImportErrorCode.DECODE_FAILED


# ── P1-5：全半角归一化别名匹配 ──────────────────────────────────────

def test_fullwidth_alias_matches(fx, tmp_path):
    from openpyxl import Workbook
    p = str(tmp_path / "fw.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["Ｎａｍｅ", "电 话"])  # 全角字母 + 全角空格
    ws.append(["客户（虚构）", "13800000000"])
    wb.save(p)
    r = parse_file(p, "fw.xlsx", _cfg(tmp_path),
                   aliases={"企业名称": ["name"], "联系电话": ["电话"]})
    assert r.alias_hits == 2
    assert r.rows[0]["Ｎａｍｅ"] == "客户（虚构）"  # payload 键保留原始表头


# ── P1-1：真实 SQLAlchemy Session 下 import_row 真实落行 ────────────

def test_real_session_writes_import_rows(fx, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    svc = ImportService(_cfg(tmp_path), factory())
    with open(fx.merged, "rb") as f:
        content = f.read()
    batch = svc.create_batch("org-1", "site-1", "workstations_merged.xlsx", content)
    r = svc.parse_batch(batch.id)
    assert batch.row_count == 5
    with Session(engine) as s:
        rows = s.execute(select(ImportRow).where(ImportRow.batch_id == batch.id)
                         .order_by(ImportRow.row_index)).scalars().all()
        assert len(rows) == 5  # P1-1 修复前这里是 0
        assert rows[0].raw_payload["区域"] == "华东区"
        assert rows[0].raw_payload["区域"] == rows[2].raw_payload["区域"]
        # 重解析防护：parsed 状态不允许再跑，行数不翻倍
        with pytest.raises(RuntimeError):
            svc.parse_batch(batch.id)
        assert len(s.execute(select(ImportRow)).scalars().all()) == 5


# ── P1-8：数值文本与 Excel 显示口径一致 ─────────────────────────────

def test_float_display_not_artifact(fx, tmp_path):
    from openpyxl import Workbook
    p = str(tmp_path / "f.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["数值"])
    ws["A2"] = 0.1 + 0.2  # 二进制尾差 0.30000000000000004
    ws["A3"] = 1e20
    wb.save(p)
    r = parse_file(p, "f.xlsx", _cfg(tmp_path))
    assert r.rows[0]["数值"] == "0.3"
    # 整值浮点走整型文本分支（精确、无科学计数）；非整值走 %.15g（Excel 显示口径）
    assert r.rows[1]["数值"] == "100000000000000000000"
