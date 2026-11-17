# -*- coding: utf-8 -*-
"""import_parser —— Excel/CSV source-file parsing & ingestion service (batch import pipeline).

导入源文件落盘与解析服务：.xlsx / .xls / .csv → 结构化行。
设计原则：
- 配置与密钥只从环境变量读取（IMPORT_*）；
- 所有单元格按文本读取，保留前导零；Excel 日期单元格同时保留序列号与格式化文本；
- 解析不可变：任何错误都以稳定错误码表达，绝不半途丢行；
- 依赖平台其余工单（import_batch / import_row 表、映射器列名别名）一律接口桩，
  对接点在 README「对接点」一节写明。
"""
__version__ = "1.0.0"
