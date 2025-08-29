from sqlalchemy import Column, String, Date, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship
from .database import Base

class Equipment(Base):
    __tablename__ = "equipment"
    equipment_id = Column(Integer, primary_key=True, autoincrement=False)  # stays INT if your file has numbers
    equipment_name = Column(String, nullable=False)
    camp_name = Column(String, nullable=False)
    region = Column(String, nullable=True)
    status = Column(String, nullable=False, default="ReadyToUse")
    next_maintenance_date = Column(Date, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    workorders = relationship("Workorder", back_populates="equipment")

class Workshop(Base):
    __tablename__ = "workshops"
    workshop_id = Column(String, primary_key=True)  # <— STRING PK
    camp_name = Column(String, nullable=False)
    location_lat = Column(Float, nullable=True)
    location_lon = Column(Float, nullable=True)

    workorders = relationship("Workorder", back_populates="workshop")

class Workorder(Base):
    __tablename__ = "workorders"
    workorder_number = Column(String, primary_key=True)  # your file has IDs like WO_0001 -> STRING
    equipment_id = Column(Integer, ForeignKey("equipment.equipment_id"), nullable=False)
    workorder_description = Column(String, nullable=True)
    workshop_id = Column(String, ForeignKey("workshops.workshop_id"), nullable=True)  # <— STRING FK
    maintenance_start_date = Column(Date, nullable=True)
    maintenance_end_date = Column(Date, nullable=True)

    equipment = relationship("Equipment", back_populates="workorders")
    workshop = relationship("Workshop", back_populates="workorders")
