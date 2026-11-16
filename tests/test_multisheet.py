# -*- coding: utf-8 -*-
"""多 sheet：清单返回 + 默认第一个非空 sheet + 显式选择与错误。"""
import pytest

from import_parser.errors import ImportErrorCode, ImportValidationError
from import_parser.parser import parse_file


def test_sheet_list_and_default_first_nonempty(fx, cfg):
    r = parse_file(fx.multisheet, "multisheet.xlsx", cfg)
    assert [s.name for s in r.sheets] == ["说明", "工位明细", "历史记录"]
    assert [s.non_empty_rows for s in r.sheets] == [1, 2, 2]
    # 工单口径：默认第一个非空 sheet——「说明」页非空（1 行）即被选中，
    # 语义固化见 test_default_semantics；用户可用清单显式切换。
    assert r.sheet_used == "说明"


def test_default_semantics(fx, cfg):
    """工单口径「默认第一个非空 sheet」：说明页只有 1 行文字也算非空。

    这里固化语义：非空 = 该页存在非空单元格行；标题页被默认选中是口径的忠实
    实现，表头识别（前 10 行）照常工作，调用方可用显式 sheet_name 或清单让
    用户选择。若核心团队希望「非空」更严格（≥2 行），在集成时调整 SheetInfo
    计算即可——README 已写明该口径。
    """
    r = parse_file(fx.multisheet, "multisheet.xlsx", cfg)
    assert r.sheet_used == "说明"
    # 表头识别会在前 10 行找到唯一非空行作为表头
    assert r.headers == ["本页无数据表"]
    assert len(r.rows) == 0


def test_explicit_sheet_selection(fx, cfg):
    r = parse_file(fx.multisheet, "multisheet.xlsx", cfg, sheet_name="历史记录")
    assert r.sheet_used == "历史记录"
    assert r.headers == ["月份", "退租数"]
    assert r.rows == [{"月份": "2024-01", "退租数": "2"}]


def test_sheet_not_found(fx, cfg):
    with pytest.raises(ImportValidationError) as e:
        parse_file(fx.multisheet, "multisheet.xlsx", cfg, sheet_name="不存在")
    assert e.value.code == ImportErrorCode.SHEET_NOT_FOUND
