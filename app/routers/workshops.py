# app/routers/workshop.py
from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from .. import database, schemas, models, crud, utils
import pandas as pd
router = APIRouter(prefix="/workshops", tags=["Workshops"])
from typing import Optional

# -------------------------
# CRUD
# -------------------------
@router.get("/", response_model=List[schemas.WorkshopOut])
def list_workshops(
    workshop_id: Optional[str] = None,             # <-- string ID like WS_001
    camp_name: Optional[str] = None,
    location_lat: Optional[float] = None,
    location_lon: Optional[float] = None,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lon_min: Optional[float] = None,
    lon_max: Optional[float] = None,
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Workshop)

    if workshop_id:
        q = q.filter(models.Workshop.workshop_id == workshop_id)
    if camp_name:
        q = q.filter(models.Workshop.camp_name.ilike(f"%{camp_name}%"))

    # exact matches (optional)
    if location_lat is not None:
        q = q.filter(models.Workshop.location_lat == location_lat)
    if location_lon is not None:
        q = q.filter(models.Workshop.location_lon == location_lon)

    # range filters (optional)
    if lat_min is not None:
        q = q.filter(models.Workshop.location_lat >= lat_min)
    if lat_max is not None:
        q = q.filter(models.Workshop.location_lat <= lat_max)
    if lon_min is not None:
        q = q.filter(models.Workshop.location_lon >= lon_min)
    if lon_max is not None:
        q = q.filter(models.Workshop.location_lon <= lon_max)

    return q.order_by(models.Workshop.workshop_id).all()

@router.get("/{workshop_id}", response_model=schemas.WorkshopOut)
def get_workshop(workshop_id: int, db: Session = Depends(database.get_db)):
    ws = crud.get_workshop(db, workshop_id)
    if not ws:
        raise HTTPException(404, "Workshop not found")
    return ws

@router.post("/", response_model=schemas.WorkshopOut)
def create_workshop(payload: schemas.WorkshopBase, db: Session = Depends(database.get_db)):
    return crud.create_workshop(
        db,
        camp_name=payload.camp_name,
        location_lat=payload.location_lat,
        location_lon=payload.location_lon,
    )

@router.patch("/{workshop_id}", response_model=schemas.WorkshopOut)
def update_workshop(workshop_id: int, data: dict, db: Session = Depends(database.get_db)):
    try:
        return crud.update_workshop(db, workshop_id, data)
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.delete("/{workshop_id}")
def delete_workshop(workshop_id: int, db: Session = Depends(database.get_db)):
    try:
        crud.delete_workshop(db, workshop_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


# -------------------------
# Upload (.xlsx / .csv)
# -------------------------
@router.post("/upload")
async def upload_workshops(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    df = await utils.read_dataframe_any(file)
    utils.ensure_columns(df, {"workshop_id", "camp_name"})

    inserted, updated, errors = 0, 0, []
    for i, row in df.iterrows():
        try:
            wid = str(row["workshop_id"]).strip()              # <— STRING
            obj = db.get(models.Workshop, wid)
            creating = obj is None
            if creating:
                obj = models.Workshop(workshop_id=wid)

            obj.camp_name = str(row["camp_name"]).strip()
            obj.location_lat = float(row["location_lat"]) if "location_lat" in df.columns and pd.notna(row.get("location_lat")) else None
            obj.location_lon = float(row["location_lon"]) if "location_lon" in df.columns and pd.notna(row.get("location_lon")) else None

            if creating:
                db.add(obj); inserted += 1
            else:
                updated += 1
        except Exception as ex:
            errors.append(f"Row {i+2}: {ex}")

    db.commit()
    return {"inserted": inserted, "updated": updated, "errors": errors}



# -------------------------
# Export (.xlsx)
# -------------------------
@router.get("/export.xlsx")
def export_workshops(db: Session = Depends(database.get_db)):
    rows = db.query(models.Workshop).all()
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
    return utils.excel_response(df, "workshops.xlsx")
