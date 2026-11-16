# import_parser —— 会员空间平台 · 导入源文件落盘与解析服务（S2-IMP-002）

Python 3.11+ / FastAPI / SQLAlchemy 2 / PostgreSQL 16（桩交付，见「对接点」）。
只用虚构测试数据；交付物不含客户名称；无任何向境外发送数据的第三方 SDK。

## 运行与测试

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest tests -q                                     # 期望：39 passed
python scripts/make_fixtures.py                     # 在 fixtures/ 物化 ≥6 个虚构样本
```

环境变量（不设则用默认值；storage 未配置时落盘 fail-fast）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `IMPORT_MAX_FILE_MB` | `20` | 单文件大小上限（MB），超限 `FILE_TOO_LARGE` |
| `IMPORT_MAX_ROWS` | `50000` | 数据行上限，超限 `TOO_MANY_ROWS` |
| `IMPORT_STORAGE_DIR` | 无 | 源文件落盘目录，文件以批次 id 命名 |

测试结果（本机 2026-11-16，Python 3.13 / openpyxl 3.1.5 / xlrd 2.0.2）：

```
39 passed in 2.25s
```

## 功能口径（对照工单）

1. **格式**：`.xlsx`（openpyxl 只读流式）、`.xls`（xlrd 2，`formatting_info=True`）、
   `.csv`；其余后缀 → `UNSUPPORTED_FORMAT`。
2. **CSV 编码链**：BOM 字节判定 → `utf-8-sig`；无 BOM 依次尝试 `utf-8` → `gb18030`；
   三段全失败按 GB18030 替换解码兜底并记 `gb18030+replace`。识别结果写入
   `import_batch.source_encoding`。
3. **限额**：先查文件大小（`FILE_TOO_LARGE`），行数在物化阶段硬校验（`TOO_MANY_ROWS`，
   恰好等于上限不算超限）。
4. **多 sheet**：`ParseResult.sheets` 返回全部 sheet（名 + 非空行数）供选择；默认取
   **第一个非空 sheet**（口径固化：任何含非空单元格的页即"非空"——含纯标题页；
   集成方可按产品需要收紧为"≥2 行数据"，见 tests/test_multisheet.py 注释）。
5. **表头识别**：前 10 行内评分 `alias_hits*1000 + non_empty - 2*numeric_count`
   最高者为表头（纯数字单元格按数据行特征扣分——无别名配置时防止"紧凑数据行
   比表头行更满"被误选为表头）。别名来自映射器工单（本单以参数注入桩），匹配
   双方做 NFKC 归一化 + 去空白（全角字母/全角空格互通）。表头上方标题行丢弃并
   计数 `skipped_title_rows`。**已知局限**：无别名配置时极端异形文件仍可能误选，
   生产管线恒传映射器别名即可规避。
6. **表头去重**：重复表头自动追加 `_2/_3…`，空表头命名 `_空列`（合并展开后的
   同名多列常见；键覆盖 = 静默丢列，故去重并保序）。`result.headers` 为去重后键。
7. **合并单元格**：xlsx 在只读模式下 openpyxl 无 `merged_cells` API（3.1.5 实测
   AttributeError）——合并区域从 zip 内 `xl/worksheets/sheetN.xml` 的
   `<mergeCells>` 直接解析（ElementTree，兼容相对/绝对 Target），左上角值展开
   填充至覆盖的每个单元格（活跃区间法 O(rows+spans)）；左上角为空则展开为空串。
   xls 走 xlrd `merged_cells`。
8. **空白行**：完全空白行跳过并计数（`blank_rows_skipped` 含表头上方与数据区，
   `blank_rows_in_data` 单列数据区口径供映射器对账行号）。
9. **文本保真**：所有单元格按文本输出（前导零保留）；数值单元格文本化与 Excel
   显示口径一致——整值走精确整型文本，非整值 `%.15g`（规避二进制尾差如
   `0.30000000000000004`）；Excel 日期单元格**序列号 + 格式化文本双保留**——
   text 为格式化文本（纯日期 `YYYY-MM-DD`，含时间 `YYYY-MM-DD HH:MM:SS`），
   序列号经 openpyxl 官方 `to_excel` 反算后放入
   `ParseResult.date_serials[row_index][表头]` 并落 `import_row.date_serials`。
   短数据行：CSV 缺失尾部列不补键；xlsx 按 dimension 补齐为空串（openpyxl 行为）。
10. **落盘与批次**：源文件存 `IMPORT_STORAGE_DIR/{batch_id}{后缀}`（不用原文件名拼
    路径，防注入/重名）；`import_batch.file_sha256` 为文件字节级 SHA-256；
    状态机 `uploaded → parsed`，失败扩展态 `parse_failed`（含稳定 `error_code`）。
    **损坏/伪装文件**（非 zip 的 .xlsx、坏 .xls 等）同样闭环到
    `parse_failed + DECODE_FAILED`，不裸抛异常。
11. **行落库**：真实 SQLAlchemy Session 下 `parse_batch` 同步写 `import_row`
    （含 org_id/site_id 继承自批次，重解析先清旧行）——无"batch 计数 N、库里
    零行"的静默丢数据陷阱。

## 错误码

`UNSUPPORTED_FORMAT` / `FILE_TOO_LARGE` / `TOO_MANY_ROWS` / `EMPTY_FILE` /
`NO_SHEET_DATA` / `SHEET_NOT_FOUND` / `HEADER_NOT_FOUND`

## 对接点（工单口径：依赖接口用桩先行）

| 依赖 | 本单形态 | 集成动作 |
|---|---|---|
| `import_batch` / `import_row` 表 | `models.py` 交付桩（约定列齐全：UUID id/org_id/site_id/created_at/created_by/updated_at/deleted_at，软删除） | 与数据底座工单统一迁移合并 |
| 映射器列名别名 | `parse_file(aliases=...)` / `parse_batch(aliases=...)` 参数注入 | 映射器工单交付后传真实别名表 |
| 平台 Session | `service.py` 接受任意 Session（含 `InMemorySession` 桩） | 换成平台真实 Session，接口不变 |
| FastAPI 挂载 | `api.py` 导出 `import_router`（`/api/imports/batches` 三端点） | 主应用 `include_router(import_router)` |

## 目录

```
import_parser/            # 服务包（config/errors/encoding/excel/header/parser/storage/models/service/api）
tests/                    # 30 条 pytest（按 AC 分文件）
scripts/make_fixtures.py  # 物化 ≥6 个虚构样本到 fixtures/
requirements.txt
```

## 交付样本（scripts/make_fixtures.py 生成）

members_gb18030.csv / companies_utf8bom.csv / workstations_leading_zero.csv /
workstations_merged.xlsx / members_two_title_rows.xlsx / multisheet.xlsx /
contracts_dates.xlsx / toomanyrows.csv / not_a_table.txt —— 全部虚构数据。
