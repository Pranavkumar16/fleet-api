# app/utils.py
from __future__ import annotations

import datetime as dt
from io import BytesIO
from typing import Iterable

import pandas as pd
from fastapi import UploadFile, HTTPException
from starlette.responses import StreamingResponse


# -------------------------
# Date parsing
# -------------------------
def parse_any_date(value):
    """Accept dd-mm-yyyy / yyyy-mm-dd / dd/mm/yyyy / yyyy/mm/dd / Excel serials."""
    if value in (None, "", "nan"):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value

    s = str(value).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    try:  # Excel serials
        serial = float(s)
        excel_epoch = dt.datetime(1899, 12, 30)
        return (excel_epoch + dt.timedelta(days=serial)).date()
    except Exception:
        return None


# -------------------------
# DataFrame helpers
# -------------------------
def df_normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    missing = set(required) - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(sorted(missing))}")

async def read_dataframe_any(file: UploadFile) -> pd.DataFrame:
    name = (file.filename or "").lower()
    content = await file.read()
    if name.endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        df = pd.read_excel(BytesIO(content))
    elif name.endswith(".csv"):
        df = pd.read_csv(BytesIO(content))
    else:
        raise HTTPException(400, "Unsupported file type. Please upload .xlsx or .csv")
    return df_normalize_columns(df)


# -------------------------
# Excel download
# -------------------------
def excel_response(df: pd.DataFrame, filename: str) -> StreamingResponse:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
