from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from fastapi import Request

from app.database import engine
from app import models, config


class SimpleAuth(AuthenticationBackend):
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


# --- Admin Views ---
class EquipmentAdmin(ModelView, model=models.Equipment):
    name_plural = "Equipments"
    column_list = [
        models.Equipment.equipment_id,
        models.Equipment.equipment_name,
        models.Equipment.camp_name,
        models.Equipment.region,
        models.Equipment.status,
        models.Equipment.start_date,
        models.Equipment.end_date,
        models.Equipment.next_maintenance_date,
    ]
    column_searchable_list = column_list   # all columns searchable
    column_sortable_list = column_list     # all columns sortable


class WorkshopAdmin(ModelView, model=models.Workshop):
    column_list = [
        models.Workshop.workshop_id,
        models.Workshop.camp_name,
        models.Workshop.location_lat,
        models.Workshop.location_lon,
    ]
    column_searchable_list = column_list
    column_sortable_list = column_list


class WorkorderAdmin(ModelView, model=models.Workorder):
    column_list = [
        models.Workorder.workorder_number,
        models.Workorder.equipment_id,
        models.Workorder.workorder_description,
        models.Workorder.workshop_id,
        models.Workorder.maintenance_start_date,
        models.Workorder.maintenance_end_date,
    ]
    column_searchable_list = column_list
    column_sortable_list = column_list


def setup_admin(app):
    admin = Admin(app, engine, authentication_backend=SimpleAuth(config.settings.SECRET_KEY))
    admin.add_view(EquipmentAdmin)
    admin.add_view(WorkshopAdmin)
    admin.add_view(WorkorderAdmin)
