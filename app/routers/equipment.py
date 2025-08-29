# app/routers/equipment.py
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
from .. import database, schemas, models, utils
from datetime import date
router = APIRouter(prefix="/equipment", tags=["Equipment"])
ALLOWED_STATUS = {"ReadyToUse", "UnderMaintenance", "Allocated"}
# -------------------------
# CRUD
# -------------------------
# at top:
from datetime import date

@router.get("/", response_model=List[schemas.EquipmentOut])
def list_equipment(
    equipment_id: Optional[int] = None,
    equipment_name: Optional[str] = None,
    camp_name: Optional[str] = None,
    region: Optional[str] = None,
    status: Optional[str] = None,
    # date filters (exact or ranges)
    start_date_from: Optional[date] = None,
    start_date_to: Optional[date] = None,
    end_date_from: Optional[date] = None,
    end_date_to: Optional[date] = None,
    next_maintenance_from: Optional[date] = None,
    next_maintenance_to: Optional[date] = None,
    db: Session = Depends(database.get_db),
):
    q = db.query(models.Equipment)

    if equipment_id is not None:
        q = q.filter(models.Equipment.equipment_id == equipment_id)
    if equipment_name:
        q = q.filter(models.Equipment.equipment_name.ilike(f"%{equipment_name}%"))
    if camp_name:
        q = q.filter(models.Equipment.camp_name.ilike(f"%{camp_name}%"))
    if region:
        q = q.filter(models.Equipment.region.ilike(f"%{region}%"))
    if status:
        q = q.filter(models.Equipment.status == status)

    if start_date_from:
        q = q.filter(models.Equipment.start_date >= start_date_from)
    if start_date_to:
        q = q.filter(models.Equipment.start_date <= start_date_to)

    if end_date_from:
        q = q.filter(models.Equipment.end_date >= end_date_from)
    if end_date_to:
        q = q.filter(models.Equipment.end_date <= end_date_to)

    if next_maintenance_from:
        q = q.filter(models.Equipment.next_maintenance_date >= next_maintenance_from)
    if next_maintenance_to:
        q = q.filter(models.Equipment.next_maintenance_date <= next_maintenance_to)

    return q.order_by(models.Equipment.equipment_id).all()



@router.get("/{equipment_id}", response_model=schemas.EquipmentOut)
def get_equipment(equipment_id: int, db: Session = Depends(database.get_db)):
    obj = db.query(models.Equipment).get(equipment_id)
    if not obj:
        raise HTTPException(404, "Equipment not found")
    return obj


@router.post("/", response_model=schemas.EquipmentOut)
def create_equipment(payload: schemas.EquipmentCreate, db: Session = Depends(database.get_db)):
    status = payload.status or "ReadyToUse"
    if status not in ALLOWED_STATUS:
        raise HTTPException(400, f"Invalid status. Allowed: {', '.join(sorted(ALLOWED_STATUS))}")

    obj = models.Equipment(
        equipment_name=payload.equipment_name.strip(),
        camp_name=payload.camp_name.strip(),
        region=(payload.region.strip() if payload.region else None),
        status=status,
        start_date=payload.start_date,
        end_date=payload.end_date,
        next_maintenance_date=payload.next_maintenance_date,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{equipment_id}", response_model=schemas.EquipmentOut)
def update_equipment(
    equipment_id: int,
    data: dict,  # partial update; keys like EquipmentBase
    db: Session = Depends(database.get_db),
):
    obj = db.query(models.Equipment).get(equipment_id)
    if not obj:
        raise HTTPException(404, "Equipment not found")

    if "status" in data and data["status"] is not None:
        if data["status"] not in ALLOWED_STATUS:
            raise HTTPException(400, f"Invalid status. Allowed: {', '.join(sorted(ALLOWED_STATUS))}")

    for k in (
        "equipment_name",
        "camp_name",
        "region",
        "status",
        "start_date",
        "end_date",
        "next_maintenance_date",
    ):
        if k in data and data[k] is not None:
            setattr(obj, k, data[k])

    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{equipment_id}")
def delete_equipment(equipment_id: int, db: Session = Depends(database.get_db)):
    obj = db.query(models.Equipment).get(equipment_id)
    if not obj:
        raise HTTPException(404, "Equipment not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}


# -------------------------
# Upload (.xlsx / .csv)
# -------------------------
@router.post("/upload")
async def upload_equipment(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    """
    Required columns (case-insensitive):
      - equipment_id  (int)
      - equipment_name
      - camp_name
    Optional:
      - region, status [ReadyToUse|UnderMaintenance|Allocated],
      - next_maintenance_date, start_date, end_date
    """
    import pandas as pd

    df = await utils.read_dataframe_any(file)           # handles xlsx/csv + normalizes headers
    utils.ensure_columns(df, {"equipment_id", "equipment_name", "camp_name"})

    inserted, updated, errors = 0, 0, []
    for i, row in df.iterrows():
        try:
            eid = int(row["equipment_id"])

            # fetch existing (UPSERT)
            obj = db.get(models.Equipment, eid)
            creating = obj is None
            if creating:
                obj = models.Equipment(equipment_id=eid)

            # validate/assign
            name = str(row["equipment_name"]).strip()
            camp = str(row["camp_name"]).strip()
            if not name or not camp:
                raise ValueError("equipment_name and camp_name are mandatory")

            obj.equipment_name = name
            obj.camp_name = camp
            obj.region = (str(row["region"]).strip()
                          if "region" in df.columns and pd.notna(row.get("region")) else None)

            status = (str(row["status"]).strip()
                      if "status" in df.columns and pd.notna(row.get("status")) else "ReadyToUse")
            if status not in {"ReadyToUse", "UnderMaintenance", "Allocated"}:
                raise ValueError(f"invalid status '{status}'")
            obj.status = status

            obj.next_maintenance_date = utils.parse_any_date(row.get("next_maintenance_date")) \
                if "next_maintenance_date" in df.columns else None
            obj.start_date = utils.parse_any_date(row.get("start_date")) \
                if "start_date" in df.columns else None
            obj.end_date = utils.parse_any_date(row.get("end_date")) \
                if "end_date" in df.columns else None

            if creating:
                db.add(obj)
                inserted += 1
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
def export_equipment(db: Session = Depends(database.get_db)):
    rows = db.query(models.Equipment).all()
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
    return utils.excel_response(df, "equipment.xlsx")
