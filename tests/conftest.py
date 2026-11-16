# -*- coding: utf-8 -*-
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from import_parser.config import ImportConfig  # noqa: E402
from import_parser.fixtures import (  # noqa: E402
    make_csv_bom, make_csv_gb18030, make_csv_leading_zero, make_csv_many_rows,
    make_txt, make_xlsx_dates, make_xlsx_merged, make_xlsx_multisheet,
    make_xlsx_two_title_rows,
)


@pytest.fixture(scope="session")
def fx(tmp_path_factory):
    """会话级虚构测试文件目录（只读使用）。"""
    d = tmp_path_factory.mktemp("fixtures")
    out = type("Fx", (), {})
    out.dir = str(d)
    out.gb18030 = str(d / "members_gb18030.csv")
    out.bom = str(d / "companies_utf8bom.csv")
    out.leading_zero = str(d / "workstations_leading_zero.csv")
    out.merged = str(d / "workstations_merged.xlsx")
    out.two_titles = str(d / "members_two_title_rows.xlsx")
    out.multisheet = str(d / "multisheet.xlsx")
    out.dates = str(d / "contracts_dates.xlsx")
    out.txt = str(d / "not_a_table.txt")
    make_csv_gb18030(out.gb18030)
    make_csv_bom(out.bom)
    make_csv_leading_zero(out.leading_zero)
    make_xlsx_merged(out.merged)
    make_xlsx_two_title_rows(out.two_titles)
    make_xlsx_multisheet(out.multisheet)
    make_xlsx_dates(out.dates)
    make_txt(out.txt)
    return out


@pytest.fixture()
def cfg(tmp_path):
    return ImportConfig.for_test(storage_dir=str(tmp_path / "storage"))
