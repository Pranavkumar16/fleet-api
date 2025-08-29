# app/crud.py
from __future__ import annotations

from typing import Iterable, Optional
from sqlalchemy.orm import Session

from . import models


# -------------------------
# Generic helpers
# -------------------------
def _apply_updates(obj, data: dict[str, object], allowed: Iterable[str]) -> None:
    for k in allowed:
        if k in data and data[k] is not None:
            setattr(obj, k, data[k])


# -------------------------
# Workshops
# -------------------------
def get_workshop(db: Session, workshop_id: int) -> Optional[models.Workshop]:
    return db.query(models.Workshop).get(workshop_id)

def list_workshops(db: Session, *, skip: int = 0, limit: int = 200):
    return db.query(models.Workshop).offset(skip).limit(limit).all()

def create_workshop(
    db: Session,
    *,
    camp_name: str,
    location_lat: float | None = None,
    location_lon: float | None = None,
) -> models.Workshop:
    ws = models.Workshop(
        camp_name=camp_name,
        location_lat=location_lat,
        location_lon=location_lon,
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws

def update_workshop(
    db: Session,
    workshop_id: int,
    data: dict[str, object],
) -> models.Workshop:
    ws = get_workshop(db, workshop_id)
    if not ws:
        raise ValueError("Workshop not found")
    _apply_updates(ws, data, ("camp_name", "location_lat", "location_lon"))
    db.commit()
    db.refresh(ws)
    return ws

def delete_workshop(db: Session, workshop_id: int) -> None:
    ws = get_workshop(db, workshop_id)
    if not ws:
        raise ValueError("Workshop not found")
    db.delete(ws)
    db.commit()


# -------------------------
# Workorders
# -------------------------
def get_workorder(db: Session, workorder_number: int) -> Optional[models.Workorder]:
    return db.query(models.Workorder).get(workorder_number)

def list_workorders(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 200,
    equipment_id: int | None = None,
    workshop_id: int | None = None,
):
    q = db.query(models.Workorder)
    if equipment_id is not None:
        q = q.filter(models.Workorder.equipment_id == equipment_id)
    if workshop_id is not None:
        q = q.filter(models.Workorder.workshop_id == workshop_id)
    return q.offset(skip).limit(limit).all()

def create_workorder(
    db: Session,
    *,
    equipment_id: int,
    workorder_description: str | None = None,
    workshop_id: int | None = None,
    maintenance_start_date=None,
    maintenance_end_date=None,
) -> models.Workorder:
    wo = models.Workorder(
        equipment_id=equipment_id,
        workorder_description=workorder_description,
        workshop_id=workshop_id,
        maintenance_start_date=maintenance_start_date,
        maintenance_end_date=maintenance_end_date,
    )
    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo

def update_workorder(
    db: Session,
    workorder_number: int,
    data: dict[str, object],
) -> models.Workorder:
    wo = get_workorder(db, workorder_number)
    if not wo:
        raise ValueError("Workorder not found")
    _apply_updates(
        wo,
        data,
        (
            "equipment_id",
            "workorder_description",
            "workshop_id",
            "maintenance_start_date",
            "maintenance_end_date",
        ),
    )
    db.commit()
    db.refresh(wo)
    return wo

def delete_workorder(db: Session, workorder_number: int) -> None:
    wo = get_workorder(db, workorder_number)
    if not wo:
        raise ValueError("Workorder not found")
    db.delete(wo)
    db.commit()
