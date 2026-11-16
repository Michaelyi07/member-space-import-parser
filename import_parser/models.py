# -*- coding: utf-8 -*-
"""批次持久化（接口桩口径）：import_batch / import_row 按《统一技术约定》建模。

对接点（README 同步说明）：
- import_batch / import_row 表结构由「数据底座」工单统一定义；本服务给出
  与约定列一致的 SQLAlchemy 模型作为交付桩，集成时由核心团队替换/合并迁移；
- mapper_aliases（映射器列名别名）来自映射器工单，本服务函数签名上以参数注入。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConventionMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportBatch(Base, ConventionMixin):
    """导入批次。状态机：uploaded → parsed（成功）/ parse_failed（扩展态，显式记录失败）。"""
    __tablename__ = "import_batch"

    original_filename: Mapped[str] = mapped_column(String(255))
    """仅用于界面展示与审计；落盘路径一律以批次 id 命名，不拼原文件名。"""
    stored_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    source_encoding: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sheet_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sheet_list_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    header_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    blank_rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportRow(Base, ConventionMixin):
    """解析结果行：raw_payload 键=原始表头，值=字符串。"""
    __tablename__ = "import_row"

    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    """数据区内 0-based 行号（不含表头与被跳过的空白行），供映射器对账。"""
    raw_payload: Mapped[dict] = mapped_column(JSON)
    date_serials: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """日期单元格 {表头: Excel 原始序列号}（双保留口径；无日期列时为 NULL）。"""
