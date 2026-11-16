# -*- coding: utf-8 -*-
"""服务层：批次创建（uploaded）→ 解析（parsed / parse_failed）→ 行落库。

内存会话桩：SQLAlchemy Session 注入即可用真实库；提供 InMemorySession 供
无库环境（本工单交付阶段）运行与测试。集成时由核心团队替换为真实 Session，
接口不变——对接点见 README。
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .config import ImportConfig
from .errors import ImportErrorCode, ImportValidationError
from .models import ImportBatch, ImportRow
from .parser import ParseResult, parse_file
from .storage import store_source


@dataclass
class InMemoryRow:
    batch_id: str
    row_index: int
    raw_payload: dict
    date_serials: dict | None = None


@dataclass
class InMemorySession:
    """无库环境桩：仅实现本服务用到的 add/commit/查询面。"""
    batches: dict[str, ImportBatch] = field(default_factory=dict)
    rows: list[InMemoryRow] = field(default_factory=list)
    committed: int = 0

    def add(self, obj):
        if isinstance(obj, ImportBatch):
            self.batches[obj.id] = obj
        elif isinstance(obj, InMemoryRow):
            self.rows.append(obj)

    def commit(self):
        self.committed += 1

    def query_batch(self, batch_id: str) -> ImportBatch | None:
        return self.batches.get(batch_id)


class ImportService:
    def __init__(self, cfg: ImportConfig, session: Session | InMemorySession):
        self.cfg = cfg
        self.session = session

    def create_batch(self, org_id: str, site_id: str, original_name: str,
                     content: bytes, created_by: str | None = None) -> ImportBatch:
        """落盘 + 建批次（status=uploaded，含 SHA-256）。格式/大小校验前置。"""
        batch = ImportBatch(id=str(uuid.uuid4()), org_id=org_id, site_id=site_id,
                            original_filename=original_name,
                            created_by=created_by)
        batch.status = "uploaded"  # SQLAlchemy default 仅在 flush 时生效，显式赋值保证内存态一致
        # 先定后缀校验（storage 内部会二次兜底），再落盘
        path, size = store_source(self.cfg, batch.id, original_name, content)
        batch.stored_path = path
        batch.file_size = size
        batch.file_sha256 = hashlib.sha256(content).hexdigest()
        self.session.add(batch)
        self.session.commit()
        return batch

    def parse_batch(self, batch_id: str,
                    aliases: dict[str, list[str]] | None = None,
                    sheet_name: str | None = None) -> ParseResult:
        """uploaded → parsed；失败置 parse_failed 并记录稳定错误码后原样抛出。"""
        batch = self.session.query_batch(batch_id) if isinstance(
            self.session, InMemorySession) else self.session.get(ImportBatch, batch_id)
        if batch is None:
            raise LookupError(f"batch {batch_id} 不存在")
        if batch.status not in ("uploaded", "parse_failed"):
            raise RuntimeError(f"batch {batch_id} 状态 {batch.status} 不可解析")
        try:
            result = parse_file(batch.stored_path, batch.original_filename,
                                self.cfg, aliases=aliases, sheet_name=sheet_name)
        except ImportValidationError as e:
            batch.status = "parse_failed"
            batch.error_code = e.code
            batch.error_detail = e.detail
            self.session.commit()
            raise
        except Exception as e:
            # P1-2（审查修复）：损坏/伪装文件（BadZipFile/KeyError/xlrd 异常等）
            # 不再裸穿透——批次闭环到 parse_failed + 稳定错误码，原始异常链保留
            batch.status = "parse_failed"
            batch.error_code = ImportErrorCode.DECODE_FAILED
            batch.error_detail = f"{type(e).__name__}: {e}"[:500]
            self.session.commit()
            raise ImportValidationError(
                ImportErrorCode.DECODE_FAILED,
                f"文件无法解析（疑似损坏或格式不符）：{type(e).__name__}: {e}") from e
        self._fill_batch_from_result(batch, result)
        self.session.commit()
        return result

    def _fill_batch_from_result(self, batch: ImportBatch, r: ParseResult) -> None:
        batch.status = "parsed"
        batch.source_encoding = r.encoding
        batch.sheet_used = r.sheet_used
        batch.sheet_list_json = {"sheets": [s.__dict__ for s in r.sheets]}
        batch.header_row_index = r.header_row_index
        batch.row_count = len(r.rows)
        batch.blank_rows_skipped = r.blank_rows_skipped
        batch.error_code = None
        batch.error_detail = None
        if isinstance(self.session, InMemorySession):
            self.session.rows = [x for x in self.session.rows
                                 if x.batch_id != batch.id]
            for idx, payload in enumerate(r.rows):
                self.session.add(InMemoryRow(
                    batch_id=batch.id, row_index=idx, raw_payload=payload,
                    date_serials=r.date_serials.get(idx)))
        else:
            # P1-1（审查修复）：真实 Session 下同样落 import_row——
            # 否则 batch.row_count=N 而库中零行的静默丢数据陷阱
            self.session.query(ImportRow).filter(
                ImportRow.batch_id == batch.id).delete()
            for idx, payload in enumerate(r.rows):
                self.session.add(ImportRow(
                    batch_id=batch.id, row_index=idx, raw_payload=payload,
                    date_serials=r.date_serials.get(idx),
                    org_id=batch.org_id, site_id=batch.site_id,
                    created_by=batch.created_by))
