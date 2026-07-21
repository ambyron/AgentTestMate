"""Dataset management API endpoints."""

import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User
from app.config import settings

router = APIRouter(prefix="/datasets", tags=["Datasets"])

# ── Upload rate limiter (per user) ──────────────────────────────
_upload_locks: defaultdict = defaultdict(asyncio.Lock)
_upload_timestamps: defaultdict[str, list[float]] = defaultdict(list)
_MAX_CONCURRENT_UPLOADS = 2
_UPLOAD_WINDOW_SEC = 10
_MAX_UPLOADS_PER_WINDOW = 2


async def _check_upload_rate(user_id: str) -> None:
    """Simple in-memory rate limiter for file uploads."""
    now = time.monotonic()
    window = _upload_timestamps[user_id]
    # Prune expired entries
    while window and window[0] < now - _UPLOAD_WINDOW_SEC:
        window.pop(0)
    if len(window) >= _MAX_UPLOADS_PER_WINDOW:
        raise HTTPException(429, "上传过于频繁，请稍后重试")
    window.append(now)


async def _read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Read file with size limit. Uses Content-Length if available."""
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            413,
            f"文件过大 ({file.size / 1024 / 1024:.1f}MB)，最大允许 {max_bytes / 1024 / 1024:.0f}MB",
        )
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            413,
            f"文件过大 ({len(content) / 1024 / 1024:.1f}MB)，最大允许 {max_bytes / 1024 / 1024:.0f}MB",
        )
    return content


_MAGIC_BYTES: dict[str, bytes] = {
    ".json": b"{",
    ".csv": b"",
    ".yaml": b"",
    ".yml": b"",
    ".xlsx": b"PK\x03\x04",
}

# Valid extensions for import
_VALID_EXTENSIONS = frozenset({".json", ".csv", ".yaml", ".yml", ".xlsx"})


def _check_magic_bytes(content: bytes, ext: str) -> None:
    """Verify file content matches expected magic bytes for the extension."""
    if ext in (".yaml", ".yml"):
        # YAML can start with a wide range of characters; basic check: not binary
        if b"\x00" in content[:512]:
            raise HTTPException(400, "YAML 文件内容不合法（包含空字节）")
    elif ext in _MAGIC_BYTES:
        magic = _MAGIC_BYTES[ext]
        if magic and not content.startswith(magic):
            raise HTTPException(400, f"文件类型不匹配: 期望 {ext} 格式，但实际内容不符")


@router.post("")
async def create_dataset(data: dict, db: AsyncSession = Depends(get_db),
                         current_space: str | None = Depends(get_current_space)):
    if current_space:
        data["space_id"] = current_space
    return await repo.create_dataset(db, data)


@router.post("/import")
async def import_dataset(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                         current_space: str | None = Depends(get_current_space),
                         current_user: User = Depends(get_current_user)):
    """Import dataset from file (JSON/CSV/YAML/XLSX)."""
    # ── Rate limit ─────────────────────────────────────────────
    async with _upload_locks[current_user.id]:
        await _check_upload_rate(current_user.id)

    # ── Validate extension ─────────────────────────────────────
    ext = Path(file.filename or "data.json").suffix.lower()
    if ext not in _VALID_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件格式: {ext}（支持: {', '.join(_VALID_EXTENSIONS)}）")

    # ── Read with size limit ───────────────────────────────────
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    content = await _read_with_limit(file, max_bytes)

    # ── Magic byte check ───────────────────────────────────────
    _check_magic_bytes(content, ext)

    # ── Parse ──────────────────────────────────────────────────
    try:
        if ext == ".json":
            data = json.loads(content)
        elif ext == ".csv":
            import pandas as pd
            import io
            df = pd.read_csv(io.BytesIO(content), encoding='utf-8', keep_default_na=False)
            for col in ['objectives', 'tags', 'rule_refs']:
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda v: json.loads(v) if isinstance(v, str) and v.strip().startswith('[') else v
                    )
            data = df.to_dict(orient="records")
            import math
            cleaned = []
            for row in data:
                cleaned_row = {}
                for k, v in row.items():
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        cleaned_row[k] = None
                    elif hasattr(v, 'item'):
                        cleaned_row[k] = v.item()
                    else:
                        cleaned_row[k] = v
                cleaned.append(cleaned_row)
            data = cleaned
        elif ext in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(content)
        elif ext in (".xlsx", ".xls"):
            import pandas as pd
            import io
            import math as _math
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl' if ext == '.xlsx' else 'xlrd', keep_default_na=False)
            # If first cell is a JSON string (structured format), parse it
            if df.shape[0] == 1 and df.shape[1] == 1:
                cell_val = df.iloc[0, 0]
                if isinstance(cell_val, str) and cell_val.strip().startswith("{"):
                    data = json.loads(cell_val)
                else:
                    raise HTTPException(400, "xlsx 结构化格式要求第一个单元格为 JSON 对象")
            else:
                # Table format — same cleaning as CSV
                for col in ['objectives', 'tags', 'rule_refs']:
                    if col in df.columns:
                        df[col] = df[col].apply(
                            lambda v: json.loads(v) if isinstance(v, str) and v.strip().startswith('[') else v
                        )
                data = df.to_dict(orient="records")
                cleaned = []
                for row in data:
                    cleaned_row = {}
                    for k, v in row.items():
                        if isinstance(v, float) and (_math.isnan(v) or _math.isinf(v)):
                            cleaned_row[k] = None
                        elif hasattr(v, 'item'):
                            cleaned_row[k] = v.item()
                        else:
                            cleaned_row[k] = v
                    cleaned.append(cleaned_row)
                data = cleaned
        else:
            raise HTTPException(400, f"Unsupported format: {ext}")
    except Exception as e:
        raise HTTPException(400, f"Parse error: {e}")

    # ── Build dataset ──────────────────────────────────────────
    if isinstance(data, dict):
        dataset_info = {
            "name": data.get("name", file.filename or "imported"),
            "description": data.get("description", ""),
            "dataset_type": data.get("dataset_type", ""),
            "tags": data.get("tags", []),
        }
        if current_space:
            dataset_info["space_id"] = current_space
        cases = data.get("test_cases", data.get("cases", []))
    elif isinstance(data, list):
        dataset_info = {"name": file.filename or "imported"}
        if current_space:
            dataset_info["space_id"] = current_space
        cases = data
    else:
        raise HTTPException(400, "Invalid data format")

    ds = await repo.create_dataset(db, dataset_info)
    if cases:
        await repo.create_test_cases_batch(db, ds.id, cases)
    return {"dataset": ds, "cases_imported": len(cases)}


@router.get("")
async def list_datasets(dataset_type: str | None = None, search: str | None = None,
                        db: AsyncSession = Depends(get_db),
                        current_space: str | None = Depends(get_current_space)):
    return await repo.list_datasets(db, space_id=current_space, dataset_type=dataset_type, search=search)


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, page: int = 1, size: int = 1000,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      current_space: str | None = Depends(get_current_space)):
    ds = await repo.get_dataset(db, dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    if not await repo.verify_space_access(db, repo.Dataset, dataset_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    cases, total = await repo.list_test_cases(db, dataset_id, page, size)
    return {"dataset": ds, "test_cases": cases, "total": total, "page": page, "size": size}


@router.put("/{dataset_id}")
async def update_dataset(dataset_id: str, data: dict, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user),
                          current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Dataset, dataset_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    ds = await repo.update_dataset(db, dataset_id, data)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user),
                          current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Dataset, dataset_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_dataset(db, dataset_id):
        raise HTTPException(404, "Dataset not found")


@router.get("/{dataset_id}/export")
async def export_dataset(dataset_id: str, format: str = "json", db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user),
                          current_space: str | None = Depends(get_current_space)):
    from fastapi.responses import PlainTextResponse
    if not await repo.verify_space_access(db, repo.Dataset, dataset_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    ds = await repo.get_dataset(db, dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    cases, _ = await repo.list_test_cases(db, dataset_id, page=1, size=10_000)
    export = {
        "name": ds.name,
        "description": ds.description,
        "dataset_type": ds.dataset_type,
        "test_cases": [
            {"case_id": c.case_id, "input": c.input, "expected_output": c.expected_output,
             "objectives": c.objectives}
            for c in cases
        ],
    }
    if format == "yaml":
        import yaml
        return PlainTextResponse(yaml.dump(export, allow_unicode=True), media_type="text/yaml")
    return export
