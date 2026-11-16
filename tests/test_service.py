# -*- coding: utf-8 -*-
"""服务层：批次状态机 uploaded → parsed / parse_failed，落盘与 SHA-256。"""
import hashlib

import pytest

from import_parser.config import ImportConfig
from import_parser.errors import ImportErrorCode, ImportValidationError
from import_parser.fixtures import make_csv_many_rows
from import_parser.parser import parse_file
from import_parser.service import ImportService, InMemorySession


def _svc(tmp_path, max_rows=50000) -> tuple[ImportService, InMemorySession, ImportConfig]:
    cfg = ImportConfig.for_test(storage_dir=str(tmp_path / "storage"), max_rows=max_rows)
    session = InMemorySession()
    return ImportService(cfg, session), session, cfg


def test_create_batch_stores_by_batch_id(tmp_path):
    svc, session, cfg = _svc(tmp_path)
    content = "编号,名称\n0001,甲（虚构）\n".encode("utf-8")
    batch = svc.create_batch("org-1", "site-1", "会员表.csv", content, created_by="tester")
    assert batch.status == "uploaded"
    assert batch.file_sha256 == hashlib.sha256(content).hexdigest()
    # 落盘路径以批次 id 命名，不含原文件名（防注入/重名）
    assert batch.id in batch.stored_path
    assert "会员表" not in batch.stored_path
    assert batch.stored_path.endswith(".csv")
    import os
    assert os.path.exists(batch.stored_path)


def test_parse_batch_success_flow(fx, tmp_path):
    svc, session, cfg = _svc(tmp_path)
    content = "编号,姓名\n0001,张伟明\n".encode("utf-8")
    batch = svc.create_batch("org-1", "site-1", "m.csv", content)
    result = svc.parse_batch(batch.id)
    assert batch.status == "parsed"
    assert result.file_sha256 == batch.file_sha256
    assert session.rows[0].raw_payload == {"编号": "0001", "姓名": "张伟明"}
    assert session.rows[0].row_index == 0
    assert session.committed >= 2


def test_parse_xlsx_full_flow(fx, tmp_path):
    svc, session, cfg = _svc(tmp_path)
    with open(fx.merged, "rb") as f:
        content = f.read()
    batch = svc.create_batch("org-1", "site-1", "workstations_merged.xlsx", content)
    svc.parse_batch(batch.id)
    assert batch.status == "parsed"
    assert batch.row_count == 5
    assert [r.raw_payload["区域"] for r in session.rows] == ["华东区"] * 3 + ["华南区"] * 2
    assert batch.source_encoding is None  # 仅 CSV 记录编码


def test_parse_failure_marks_batch_small_limit(tmp_path):
    svc, session, cfg = _svc(tmp_path, max_rows=5)
    content = ("编号,名称\n" + "".join(f"{i:06d},行{i}\n" for i in range(20))).encode("utf-8")
    batch = svc.create_batch("org-1", "site-1", "big.csv", content)
    with pytest.raises(ImportValidationError) as e:
        svc.parse_batch(batch.id)
    assert e.value.code == ImportErrorCode.TOO_MANY_ROWS
    assert batch.status == "parse_failed"
    assert batch.error_code == ImportErrorCode.TOO_MANY_ROWS


def test_reparse_blocked_after_success(fx, tmp_path):
    """已 parsed 的批次不可重复解析（幂等保护；重导应建新批次）。"""
    svc, session, cfg = _svc(tmp_path)
    batch = svc.create_batch("org-1", "site-1", "m.csv", "a,b\n1,2\n".encode("utf-8"))
    svc.parse_batch(batch.id)
    with pytest.raises(RuntimeError):
        svc.parse_batch(batch.id)


def test_unknown_batch_lookup_error(tmp_path):
    svc, session, cfg = _svc(tmp_path)
    with pytest.raises(LookupError):
        svc.parse_batch("no-such-batch")


def test_sha_matches_file_on_disk(fx, tmp_path):
    """file_sha256 与落盘文件字节一致（ SHA 在落盘后仍应可复核）。"""
    svc, session, cfg = _svc(tmp_path)
    content = "a,b\n1,2\n".encode("utf-8")
    batch = svc.create_batch("org-1", "site-1", "m.csv", content)
    disk = open(batch.stored_path, "rb").read()
    assert hashlib.sha256(disk).hexdigest() == batch.file_sha256
    # 平台外发用的 parse_file 也能复核
    r = parse_file(batch.stored_path, "m.csv", cfg)
    assert r.file_sha256 == batch.file_sha256
