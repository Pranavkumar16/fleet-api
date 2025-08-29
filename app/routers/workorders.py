# app/routers/workorder.py
from __future__ import annotations
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from .. import database, schemas, models, crud, utils
import pandas as pd
router = APIRouter(prefix="/workorders", tags=["Workorders"])


# -------------------------
# CRUD
# -------------------------
@router.get("/", response_model=List[schemas.WorkorderOut])
def list_workorders(
    workorder_number: Optional[str] = None,            # <-- string ID
    equipment_id: Optional[int] = None,
    workshop_id: Optional[str] = None,                 # <-- string FK
    workorder_description: Optional[str] = None,
    maintenance_start_from: Optional[date] = None,
    maintenance_start_to: Optional[date] = None,
    maintenance_end_from: Optional[date] = None,
    maintenance_end_to: Optional[date] = None,
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Workorder)

    if workorder_number:
        q = q.filter(models.Workorder.workorder_number == workorder_number)
    if equipment_id is not None:
        q = q.filter(models.Workorder.equipment_id == equipment_id)
    if workshop_id:
        q = q.filter(models.Workorder.workshop_id == workshop_id)
    if workorder_description:
        q = q.filter(models.Workorder.workorder_description.ilike(f"%{workorder_description}%"))

    if maintenance_start_from:
        q = q.filter(models.Workorder.maintenance_start_date >= maintenance_start_from)
    if maintenance_start_to:
        q = q.filter(models.Workorder.maintenance_start_date <= maintenance_start_to)
    if maintenance_end_from:
        q = q.filter(models.Workorder.maintenance_end_date >= maintenance_end_from)
    if maintenance_end_to:
        q = q.filter(models.Workorder.maintenance_end_date <= maintenance_end_to)

    return q.order_by(models.Workorder.workorder_number).all()

@router.get("/{workorder_number}", response_model=schemas.WorkorderOut)
def get_workorder(workorder_number: int, db: Session = Depends(database.get_db)):
    wo = crud.get_workorder(db, workorder_number)
    if not wo:
        raise HTTPException(404, "Workorder not found")
    return wo

@router.post("/", response_model=schemas.WorkorderOut)
def create_workorder(payload: schemas.WorkorderBase, db: Session = Depends(database.get_db)):
    wo = crud.create_workorder(
        db,
        equipment_id=payload.equipment_id,
        workorder_description=payload.workorder_description,
        workshop_id=payload.workshop_id,
        maintenance_start_date=payload.maintenance_start_date,
        maintenance_end_date=payload.maintenance_end_date,
    )
    return wo

@router.patch("/{workorder_number}", response_model=schemas.WorkorderOut)
def update_workorder(
    workorder_number: int,
    data: dict,  # partial update; keys same as WorkorderBase
    db: Session = Depends(database.get_db),
):
    try:
        return crud.update_workorder(db, workorder_number, data)
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.delete("/{workorder_number}")
def delete_workorder(workorder_number: int, db: Session = Depends(database.get_db)):
    try:
        crud.delete_workorder(db, workorder_number)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


# -------------------------
# Upload (.xlsx / .csv)
# -------------------------
@router.post("/upload")
async def upload_workorders(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    df = await utils.read_dataframe_any(file)
    utils.ensure_columns(df, {"workorder_number", "equipment_id"})

    inserted, updated, errors = 0, 0, []
    for i, row in df.iterrows():
        try:
            won = str(row["workorder_number"]).strip()         # STRING PK
            obj = db.get(models.Workorder, won)
            creating = obj is None
            if creating:
                obj = models.Workorder(workorder_number=won)

            obj.equipment_id = int(row["equipment_id"])        # your equipment IDs are numeric
            obj.workorder_description = (str(row["workorder_description"]).strip()
                                         if "workorder_description" in df.columns and pd.notna(row.get("workorder_description")) else None)
            obj.workshop_id = (str(row["workshop_id"]).strip()
                               if "workshop_id" in df.columns and pd.notna(row.get("workshop_id")) else None)  # <— STRING
            obj.maintenance_start_date = utils.parse_any_date(row.get("maintenance_start_date")) if "maintenance_start_date" in df.columns else None
            obj.maintenance_end_date = utils.parse_any_date(row.get("maintenance_end_date")) if "maintenance_end_date" in df.columns else None

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
def export_workorders(db: Session = Depends(database.get_db)):
    rows = db.query(models.Workorder).all()
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
    return utils.excel_response(df, "workorders.xlsx")
