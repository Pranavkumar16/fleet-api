# app.py
from __future__ import annotations

import os
import datetime as dt
from io import BytesIO
from typing import Optional, List

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Date,
    Float,
    ForeignKey,
    select,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

# --------------------------------------------------------------------------------------
# DB setup (SQLite by default; set DATABASE_URL for Postgres etc.)
# --------------------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fleet.db")
engine_kwargs = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------
class Equipment(Base):
    __tablename__ = "equipment"

    equipment_id = Column(Integer, primary_key=True, index=True)
    equipment_name = Column(String, nullable=False)
    camp_name = Column(String, nullable=False)
    region = Column(String, nullable=True)

    # Planning fields
    status = Column(String, nullable=False, default="ReadyToUse")  # ReadyToUse / UnderMaintenance / Allocated
    next_maintenance_date = Column(Date, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    workorders = relationship("Workorder", back_populates="equipment")


class Workshop(Base):
    __tablename__ = "workshops"

    workshop_id = Column(Integer, primary_key=True, index=True)
    camp_name = Column(String, nullable=False)
    location_lat = Column(Float, nullable=True)
    location_lon = Column(Float, nullable=True)


class Workorder(Base):
    __tablename__ = "workorders"

    workorder_number = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.equipment_id"), nullable=False)
    workorder_description = Column(String, nullable=True)
    workshop_id = Column(Integer, ForeignKey("workshops.workshop_id"), nullable=True)
    maintenance_start_date = Column(Date, nullable=True)
    maintenance_end_date = Column(Date, nullable=True)

    equipment = relationship("Equipment", back_populates="workorders")


Base.metadata.create_all(bind=engine)

# --------------------------------------------------------------------------------------
# App + middleware
# --------------------------------------------------------------------------------------
app = FastAPI(title="Fleet Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sessions for sqladmin
app.add_middleware(SessionMiddleware, secret_key="super-secret")

# --------------------------------------------------------------------------------------
# Local Swagger UI (version-proof; no external CDN)
# --------------------------------------------------------------------------------------
import swagger_ui_bundle  # noqa

swagger_ui_dir = None
try:
    from importlib.resources import files as _files

    swagger_ui_dir = str((_files(swagger_ui_bundle) / "swagger_ui_3"))
except Exception:
    try:
        from swagger_ui_bundle import swagger_ui_3_path as _const_path  # type: ignore

        swagger_ui_dir = _const_path
    except Exception:
        try:
            import pkg_resources

            swagger_ui_dir = os.path.join(
                pkg_resources.resource_filename("swagger_ui_bundle", ""), "swagger_ui_3"
            )
        except Exception:
            swagger_ui_dir = None

if not swagger_ui_dir or not os.path.isdir(swagger_ui_dir):
    raise RuntimeError(
        "Could not locate Swagger UI assets in swagger_ui_bundle. "
        "Install or upgrade it:  pip install -U swagger-ui-bundle"
    )

app.mount("/swagger-ui", StaticFiles(directory=swagger_ui_dir), name="swagger-ui")


@app.get("/docs", include_in_schema=False)
def local_docs():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="API Docs",
        swagger_js_url="/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui/swagger-ui.css",
    )


# --------------------------------------------------------------------------------------
# SQLAdmin (simple session auth)
# --------------------------------------------------------------------------------------
class SimpleAuth(AuthenticationBackend):
    def __init__(self, secret_key: str):
        super().__init__(secret_key=secret_key)

    async def login(self, request: Request) -> bool:
        form = await request.form()
        if form.get("username") == "admin" and form.get("password") == "secret":
            request.session.update({"user": "admin"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("user"))


admin = Admin(app, engine, authentication_backend=SimpleAuth("super-secret"), base_url="/admin")


class EquipmentAdmin(ModelView, model=Equipment):
    name_plural = "Equipments"
    column_list = [
        Equipment.equipment_id,
        Equipment.equipment_name,
        Equipment.camp_name,
        Equipment.region,
        Equipment.status,
        Equipment.next_maintenance_date,
        Equipment.start_date,
        Equipment.end_date,
    ]


class WorkshopAdmin(ModelView, model=Workshop):
    column_list = [
        Workshop.workshop_id,
        Workshop.camp_name,
        Workshop.location_lat,
        Workshop.location_lon,
    ]


class WorkorderAdmin(ModelView, model=Workorder):
    column_list = [
        Workorder.workorder_number,
        Workorder.equipment_id,
        Workorder.workorder_description,
        Workorder.workshop_id,
        Workorder.maintenance_start_date,
        Workorder.maintenance_end_date,
    ]


admin.add_view(EquipmentAdmin)
admin.add_view(WorkshopAdmin)
admin.add_view(WorkorderAdmin)


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def parse_any_date(value):
    """Accept dd-mm-yyyy / yyyy-mm-dd / dd/mm/yyyy / yyyy/mm/dd or Excel serial/date objects."""
    if value in (None, "", "nan"):
        return None
    if isinstance(value, dt.date):
        return value
    if isinstance(value, dt.datetime):
        return value.date()

    s = str(value).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    # Excel serials
    try:
        serial = float(s)
        excel_epoch = dt.datetime(1899, 12, 30)
        return (excel_epoch + dt.timedelta(days=serial)).date()
    except Exception:
        return None


def html_upload_form(title: str, action: str, back_to: str, extra_hint: str = "") -> str:
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 40px; }}
      .card {{ max-width: 520px; padding: 24px; border: 1px solid #e5e7eb; border-radius: 12px; }}
      .btn {{ background:#2563eb; color:#fff; border:none; padding:10px 16px; border-radius:8px; cursor:pointer; }}
      .btn:disabled {{ opacity:.6; cursor: not-allowed; }}
      a {{ color:#2563eb; text-decoration:none; }}
      .hint {{ font-size:.9rem; color:#64748b; }}
    </style>
  </head>
  <body>
    <h2>{title}</h2>
    <div class="card">
      <form method="post" action="{action}" enctype="multipart/form-data">
        <p><input type="file" name="file" accept=".xlsx,.xlsm,.xltx,.xltm" required></p>
        <p class="hint">{extra_hint}</p>
        <p>
          <button class="btn" type="submit">Upload</button>
          &nbsp;&nbsp;<a href="{back_to}">Back to list</a>
        </p>
      </form>
    </div>
  </body>
</html>
"""


def excel_response(df, filename: str) -> StreamingResponse:
    import pandas as pd  # lazy import

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------------------
# Upload forms (GET) – one per table
# --------------------------------------------------------------------------------------
@app.get("/admin/equipment/upload", response_class=HTMLResponse)
def form_equipment_upload():
    hint = (
        "Columns (case-insensitive): equipment_name*, camp_name*, region, "
        "status (ReadyToUse/UnderMaintenance/Allocated), "
        "next_maintenance_date, start_date, end_date"
    )
    return HTMLResponse(
        html_upload_form(
            "Upload Equipments (.xlsx)",
            "/upload/equipment",
            "/admin/equipment/list",
            hint,
        )
    )


@app.get("/admin/workshops/upload", response_class=HTMLResponse)
def form_workshops_upload():
    hint = "Columns: camp_name*, location_lat, location_lon"
    return HTMLResponse(
        html_upload_form(
            "Upload Workshops (.xlsx)",
            "/upload/workshops",
            "/admin/workshops/list",
            hint,
        )
    )


@app.get("/admin/workorders/upload", response_class=HTMLResponse)
def form_workorders_upload():
    hint = (
        "Columns: equipment_id*, workorder_description, workshop_id, "
        "maintenance_start_date, maintenance_end_date"
    )
    return HTMLResponse(
        html_upload_form(
            "Upload Workorders (.xlsx)",
            "/upload/workorders",
            "/admin/workorders/list",
            hint,
        )
    )


# --------------------------------------------------------------------------------------
# Upload handlers (POST) – one per table
# --------------------------------------------------------------------------------------
@app.post("/upload/equipment")
async def upload_equipment(file: UploadFile = File(...), db: Session = Depends(get_db)):
    import pandas as pd  # lazy

    if not file.filename.lower().endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        raise HTTPException(400, "Please upload an Excel .xlsx/.xlsm file")

    df = pd.read_excel(BytesIO(await file.read()))
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"equipment_name", "camp_name"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(sorted(missing))}")

    inserted, errors = 0, []
    for i, row in df.iterrows():
        try:
            e = Equipment(
                equipment_name=str(row["equipment_name"]).strip(),
                camp_name=str(row["camp_name"]).strip(),
                region=(str(row["region"]).strip() if "region" in df.columns and pd.notna(row.get("region")) else None),
                status=(str(row["status"]).strip() if "status" in df.columns and pd.notna(row.get("status")) else "ReadyToUse"),
                next_maintenance_date=parse_any_date(row.get("next_maintenance_date")) if "next_maintenance_date" in df.columns else None,
                start_date=parse_any_date(row.get("start_date")) if "start_date" in df.columns else None,
                end_date=parse_any_date(row.get("end_date")) if "end_date" in df.columns else None,
            )
            if not e.equipment_name or not e.camp_name:
                raise ValueError("equipment_name and camp_name are mandatory")
            db.add(e)
            inserted += 1
        except Exception as ex:
            errors.append(f"Row {i+2}: {ex}")
    db.commit()

    msg = f"Inserted: {inserted}. Errors: {len(errors)}"
    html = f"""
    <html><body style="font-family:system-ui;margin:40px">
      <h3>Equipment upload result</h3>
      <p>{msg}</p>
      <p><a href="/admin/equipment/list">Back to Equipment list</a> |
         <a href="/equipment/export.xlsx">Download Equipments</a></p>
      {'<pre style="white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:8px">' + chr(10).join(errors) + '</pre>' if errors else ''}
    </body></html>
    """
    return HTMLResponse(html)


@app.post("/upload/workshops")
async def upload_workshops(file: UploadFile = File(...), db: Session = Depends(get_db)):
    import pandas as pd  # lazy

    if not file.filename.lower().endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        raise HTTPException(400, "Please upload an Excel .xlsx/.xlsm file")

    df = pd.read_excel(BytesIO(await file.read()))
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"camp_name"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(sorted(missing))}")

    inserted, errors = 0, []
    for i, row in df.iterrows():
        try:
            ws = Workshop(
                camp_name=str(row["camp_name"]).strip(),
                location_lat=float(row["location_lat"]) if "location_lat" in df.columns and pd.notna(row.get("location_lat")) else None,
                location_lon=float(row["location_lon"]) if "location_lon" in df.columns and pd.notna(row.get("location_lon")) else None,
            )
            if not ws.camp_name:
                raise ValueError("camp_name is mandatory")
            db.add(ws)
            inserted += 1
        except Exception as ex:
            errors.append(f"Row {i+2}: {ex}")
    db.commit()

    msg = f"Inserted: {inserted}. Errors: {len(errors)}"
    html = f"""
    <html><body style="font-family:system-ui;margin:40px">
      <h3>Workshops upload result</h3>
      <p>{msg}</p>
      <p><a href="/admin/workshops/list">Back to Workshops list</a> |
         <a href="/workshops/export.xlsx">Download Workshops</a></p>
      {'<pre style="white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:8px">' + chr(10).join(errors) + '</pre>' if errors else ''}
    </body></html>
    """
    return HTMLResponse(html)


@app.post("/upload/workorders")
async def upload_workorders(file: UploadFile = File(...), db: Session = Depends(get_db)):
    import pandas as pd  # lazy

    if not file.filename.lower().endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        raise HTTPException(400, "Please upload an Excel .xlsx/.xlsm file")

    df = pd.read_excel(BytesIO(await file.read()))
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"equipment_id"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(sorted(missing))}")

    inserted, errors = 0, []
    for i, row in df.iterrows():
        try:
            wo = Workorder(
                equipment_id=int(row["equipment_id"]),
                workorder_description=(str(row["workorder_description"]).strip() if "workorder_description" in df.columns and pd.notna(row.get("workorder_description")) else None),
                workshop_id=(int(row["workshop_id"]) if "workshop_id" in df.columns and pd.notna(row.get("workshop_id")) else None),
                maintenance_start_date=parse_any_date(row.get("maintenance_start_date")) if "maintenance_start_date" in df.columns else None,
                maintenance_end_date=parse_any_date(row.get("maintenance_end_date")) if "maintenance_end_date" in df.columns else None,
            )
            db.add(wo)
            inserted += 1
        except Exception as ex:
            errors.append(f"Row {i+2}: {ex}")
    db.commit()

    msg = f"Inserted: {inserted}. Errors: {len(errors)}"
    html = f"""
    <html><body style="font-family:system-ui;margin:40px">
      <h3>Workorders upload result</h3>
      <p>{msg}</p>
      <p><a href="/admin/workorders/list">Back to Workorders list</a> |
         <a href="/workorders/export.xlsx">Download Workorders</a></p>
      {'<pre style="white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:8px">' + chr(10).join(errors) + '</pre>' if errors else ''}
    </body></html>
    """
    return HTMLResponse(html)


# --------------------------------------------------------------------------------------
# Export endpoints (download current table to Excel)
# --------------------------------------------------------------------------------------
@app.get("/equipment/export.xlsx")
def export_equipment(db: Session = Depends(get_db)):
    import pandas as pd  # lazy

    rows = db.execute(select(Equipment)).scalars().all()
    df = pd.DataFrame(
        [
            dict(
                equipment_id=r.equipment_id,
                equipment_name=r.equipment_name,
                camp_name=r.camp_name,
                region=r.region,
                status=r.status,
                next_maintenance_date=r.next_maintenance_date,
                start_date=r.start_date,
                end_date=r.end_date,
            )
            for r in rows
        ]
    )
    return excel_response(df, "equipment.xlsx")


@app.get("/workshops/export.xlsx")
def export_workshops(db: Session = Depends(get_db)):
    import pandas as pd

    rows = db.execute(select(Workshop)).scalars().all()
    df = pd.DataFrame(
        [
            dict(
                workshop_id=r.workshop_id,
                camp_name=r.camp_name,
                location_lat=r.location_lat,
                location_lon=r.location_lon,
            )
            for r in rows
        ]
    )
    return excel_response(df, "workshops.xlsx")


@app.get("/workorders/export.xlsx")
def export_workorders(db: Session = Depends(get_db)):
    import pandas as pd

    rows = db.execute(select(Workorder)).scalars().all()
    df = pd.DataFrame(
        [
            dict(
                workorder_number=r.workorder_number,
                equipment_id=r.equipment_id,
                workorder_description=r.workorder_description,
                workshop_id=r.workshop_id,
                maintenance_start_date=r.maintenance_start_date,
                maintenance_end_date=r.maintenance_end_date,
            )
            for r in rows
        ]
    )
    return excel_response(df, "workorders.xlsx")


# --------------------------------------------------------------------------------------
# Minimal REST list endpoints (optional) just to have something in /docs
# --------------------------------------------------------------------------------------
@app.get("/equipment", response_model=List[dict])
def list_equipment_api(
    equipment_name: Optional[str] = None,
    camp_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Equipment)
    if equipment_name:
        q = q.filter(Equipment.equipment_name.ilike(f"%{equipment_name}%"))
    if camp_name:
        q = q.filter(Equipment.camp_name.ilike(f"%{camp_name}%"))
    if status:
        q = q.filter(Equipment.status == status)
    rows = q.offset(offset).limit(limit).all()
    return [
        {
            "equipment_id": r.equipment_id,
            "equipment_name": r.equipment_name,
            "camp_name": r.camp_name,
            "region": r.region,
            "status": r.status,
            "next_maintenance_date": r.next_maintenance_date,
            "start_date": r.start_date,
            "end_date": r.end_date,
        }
        for r in rows
    ]


@app.get("/workshops", response_model=List[dict])
def list_workshops_api(limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.query(Workshop).offset(offset).limit(limit).all()
    return [
        {
            "workshop_id": r.workshop_id,
            "camp_name": r.camp_name,
            "location_lat": r.location_lat,
            "location_lon": r.location_lon,
        }
        for r in rows
    ]


@app.get("/workorders", response_model=List[dict])
def list_workorders_api(limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    rows = db.query(Workorder).offset(offset).limit(limit).all()
    return [
        {
            "workorder_number": r.workorder_number,
            "equipment_id": r.equipment_id,
            "workorder_description": r.workorder_description,
            "workshop_id": r.workshop_id,
            "maintenance_start_date": r.maintenance_start_date,
            "maintenance_end_date": r.maintenance_end_date,
        }
        for r in rows
    ]
