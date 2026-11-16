# -*- coding: utf-8 -*-
"""物化全部虚构测试样本到 fixtures/（工单交付口径：≥6 个测试文件）。

用法：python scripts/make_fixtures.py [输出目录，默认 ../fixtures]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from import_parser.fixtures import materialize_all  # noqa: E402


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "fixtures")
    made = materialize_all(os.path.abspath(out))
    print(f"已生成 {len(made)} 个虚构样本 → {os.path.abspath(out)}")
    for name in made:
        print(" -", name)


if __name__ == "__main__":
    main()
