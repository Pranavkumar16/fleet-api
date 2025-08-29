from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
import math
from datetime import date

from app import database, models

router = APIRouter(prefix="/demand", tags=["Demand"])

# Haversine (km)
def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

@router.post("/check")
def check_demand(
    camp_name: str,
    equipment_name: str,
    start_date: date,
    end_date: date,
    quantity: int,
    radius_km: float = 15.0,
    db: Session = Depends(database.get_db),
):
    # 1) locate the home camp coordinates
    home_ws = db.query(models.Workshop).filter(models.Workshop.camp_name.ilike(camp_name)).first()
    if not home_ws:
        raise HTTPException(404, f"Camp '{camp_name}' not found in workshops table")

    # 2) compute availability at the home camp (ReadyToUse and not overlapping)
    q_home = (
        db.query(models.Equipment)
          .filter(models.Equipment.camp_name.ilike(camp_name))
          .filter(models.Equipment.equipment_name.ilike(equipment_name))
    )

    def is_available(e: models.Equipment) -> bool:
        if e.status != "ReadyToUse":
            return False
        # if dates present, ensure no overlap with the request window
        if e.start_date and e.end_date:
            # overlap if e.start <= req.end and req.start <= e.end
            overlap = (e.start_date <= end_date) and (start_date <= e.end_date)
            return not overlap
        return True

    home_elems = [e for e in q_home.all() if is_available(e)]
    available_home = len(home_elems)
    meets = available_home >= quantity

    # 3) if home meets, no map needed
    result = {
        "camp_name": camp_name,
        "requested": {
            "equipment_name": equipment_name,
            "start_date": start_date,
            "end_date": end_date,
            "quantity": quantity,
        },
        "availability": {"available": available_home, "meets_requirement": meets},
        "ui": {
            "show_map": not meets,                          # <— INDICATOR
            "center": {"lat": home_ws.location_lat, "lon": home_ws.location_lon},
            "radius_km": radius_km,
        },
        "alternatives": [],
    }

    if meets:
        return result

    # 4) build alternatives within radius
    #    For each workshop, compute distance & counts for the requested equipment
    all_ws = db.query(models.Workshop).all()
    alts = []
    for ws in all_ws:
        if ws.camp_name.lower() == camp_name.lower():
            continue
        dist = haversine_km(home_ws.location_lat, home_ws.location_lon, ws.location_lat, ws.location_lon)
        if dist is None or dist > radius_km:
            continue

        eq = (db.query(models.Equipment)
                .filter(models.Equipment.camp_name.ilike(ws.camp_name))
                .filter(models.Equipment.equipment_name.ilike(equipment_name))
                .all())

        ready = 0
        maint = 0
        for e in eq:
            if e.status == "UnderMaintenance":
                maint += 1
            elif e.status == "ReadyToUse" and is_available(e):
                ready += 1

        alts.append({
            "camp_name": ws.camp_name,
            "workshop_id": getattr(ws, "workshop_id", None),
            "distance_km": round(dist, 1),
            "location": {"lat": ws.location_lat, "lon": ws.location_lon},
            "counts": {"ready_to_use": ready, "under_maintenance": maint}
        })

    # sort by distance, best first
    alts.sort(key=lambda x: (x["distance_km"], -x["counts"]["ready_to_use"]))
    result["alternatives"] = alts
    return result
