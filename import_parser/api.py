# -*- coding: utf-8 -*-
"""FastAPI 路由（薄壳）：业务全部在 service 层，路由只做协议转换。

集成时把 router.include_router(import_router) 挂到平台主应用即可——
对接点见 README。上传用 multipart/form-data（依赖 python-multipart）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .config import ImportConfig, _env_int
from .errors import ImportErrorCode, ImportValidationError
from .service import ImportService, InMemorySession

import_router = APIRouter(prefix="/api/imports", tags=["imports"])

_STATUS_BY_CODE = {
    ImportErrorCode.UNSUPPORTED_FORMAT: 415,
    ImportErrorCode.FILE_TOO_LARGE: 413,
    ImportErrorCode.TOO_MANY_ROWS: 422,
    ImportErrorCode.EMPTY_FILE: 422,
    ImportErrorCode.NO_SHEET_DATA: 422,
    ImportErrorCode.SHEET_NOT_FOUND: 422,
    ImportErrorCode.HEADER_NOT_FOUND: 422,
    ImportErrorCode.DECODE_FAILED: 422,
}


def get_service() -> ImportService:
    """依赖注入桩：集成时替换为「平台 Session 依赖 + 真实配置」。"""
    cfg = ImportConfig()
    return ImportService(cfg, InMemorySession())


def _to_http(e: ImportValidationError) -> HTTPException:
    return HTTPException(status_code=_STATUS_BY_CODE.get(e.code, 422),
                         detail={"code": e.code, "detail": e.detail})


@import_router.post("/batches", status_code=201)
def create_batch(file: UploadFile = File(...),
                 org_id: str = Form(...),
                 site_id: str = Form(...),
                 svc: ImportService = Depends(get_service)):
    try:
        batch = svc.create_batch(org_id, site_id, file.filename or "",
                                 file.file.read())
    except ImportValidationError as e:
        raise _to_http(e)
    return {"batch_id": batch.id, "status": batch.status,
            "file_sha256": batch.file_sha256, "file_size": batch.file_size}


@import_router.post("/batches/{batch_id}/parse")
def parse_batch(batch_id: str,
                sheet_name: str | None = Form(default=None),
                svc: ImportService = Depends(get_service)):
    try:
        r = svc.parse_batch(batch_id, sheet_name=sheet_name)
    except ImportValidationError as e:
        raise _to_http(e)
    return {
        "batch_id": batch_id, "status": "parsed",
        "file_sha256": r.file_sha256, "encoding": r.encoding,
        "sheets": [s.__dict__ for s in r.sheets], "sheet_used": r.sheet_used,
        "header_row_index": r.header_row_index,
        "skipped_title_rows": r.skipped_title_rows,
        "headers": r.headers, "row_count": len(r.rows),
        "blank_rows_skipped": r.blank_rows_skipped,
        "rows_preview": r.rows[:20],
    }


@import_router.get("/batches/{batch_id}")
def get_batch(batch_id: str, svc: ImportService = Depends(get_service)):
    batch = svc.session.query_batch(batch_id)
    if batch is None:
        raise HTTPException(404, {"code": "BATCH_NOT_FOUND"})
    return {"batch_id": batch.id, "status": batch.status,
            "original_filename": batch.original_filename,
            "file_sha256": batch.file_sha256,
            "source_encoding": batch.source_encoding,
            "sheet_used": batch.sheet_used,
            "row_count": batch.row_count,
            "error_code": batch.error_code}
