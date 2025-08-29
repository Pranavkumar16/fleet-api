from pydantic import BaseModel
from typing import Optional
from datetime import date

class EquipmentBase(BaseModel):
    equipment_name: str
    camp_name: str
    region: Optional[str] = None
    status: Optional[str] = "ReadyToUse"
    next_maintenance_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class EquipmentCreate(EquipmentBase):
    pass

class EquipmentOut(EquipmentBase):
    equipment_id: int
    class Config:
        orm_mode = True

class WorkshopBase(BaseModel):
    camp_name: str
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None

class WorkshopOut(BaseModel):
    workshop_id: str
    camp_name: str
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None

class WorkorderBase(BaseModel):
    equipment_id: int
    workorder_description: Optional[str] = None
    workshop_id: Optional[int] = None
    maintenance_start_date: Optional[date] = None
    maintenance_end_date: Optional[date] = None

class WorkorderOut(BaseModel):
    workorder_number: str
    equipment_id: int
    workshop_id: Optional[str] = None
    workorder_description: Optional[str] = None
    maintenance_start_date: Optional[date] = None
    maintenance_end_date: Optional[date] = None
