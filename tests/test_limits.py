# -*- coding: utf-8 -*-
"""AC5 + 限额与错误码：TOO_MANY_ROWS / FILE_TOO_LARGE / UNSUPPORTED_FORMAT。

行数/大小上限在测试里用小值注入（IMPORT_MAX_ROWS / IMPORT_MAX_FILE_MB 口径），
避免生成 5 万行真实文件拖慢测试；等价性由「计数发生在物化阶段」保证。
"""
import pytest

from import_parser.config import ImportConfig
from import_parser.errors import ImportErrorCode, ImportValidationError
from import_parser.fixtures import make_csv_many_rows
from import_parser.parser import parse_file


def _cfg(tmp_path, max_rows=50000, max_file_mb=20) -> ImportConfig:
    return ImportConfig.for_test(storage_dir=str(tmp_path / "storage"),
                                 max_rows=max_rows, max_file_mb=max_file_mb)


def test_too_many_rows(fx, tmp_path):
    """数据行 11 > 上限 10 → TOO_MANY_ROWS（AC5）。"""
    p = str(tmp_path / "many.csv")
    make_csv_many_rows(p, n_rows=11)
    with pytest.raises(ImportValidationError) as e:
        parse_file(p, "many.csv", _cfg(tmp_path, max_rows=10))
    assert e.value.code == ImportErrorCode.TOO_MANY_ROWS


def test_exact_boundary_ok(fx, tmp_path):
    """恰好等于上限（10 行 = 上限 10）应成功——只有 > 才算超限。"""
    p = str(tmp_path / "edge.csv")
    make_csv_many_rows(p, n_rows=10)
    r = parse_file(p, "edge.csv", _cfg(tmp_path, max_rows=10))
    assert len(r.rows) == 10


def test_file_too_large(fx, tmp_path):
    p = str(tmp_path / "big.csv")
    make_csv_many_rows(p, n_rows=120000)  # ≈2.2MB
    with pytest.raises(ImportValidationError) as e:
        parse_file(p, "big2.csv" if False else "big.csv", _cfg(tmp_path, max_file_mb=1))
    assert e.value.code == ImportErrorCode.FILE_TOO_LARGE


def test_unsupported_format(fx, cfg):
    with pytest.raises(ImportValidationError) as e:
        parse_file(fx.txt, "not_a_table.txt", cfg)
    assert e.value.code == ImportErrorCode.UNSUPPORTED_FORMAT


def test_no_suffix_unsupported(fx, tmp_path, cfg):
    p = str(tmp_path / "noext")
    with open(p, "w", encoding="utf-8") as f:
        f.write("a,b\n1,2\n")
    with pytest.raises(ImportValidationError) as e:
        parse_file(p, "noext", cfg)
    assert e.value.code == ImportErrorCode.UNSUPPORTED_FORMAT


def test_empty_file(fx, tmp_path, cfg):
    p = str(tmp_path / "empty.csv")
    open(p, "wb").close()
    with pytest.raises(ImportValidationError) as e:
        parse_file(p, "empty.csv", cfg)
    assert e.value.code == ImportErrorCode.EMPTY_FILE
