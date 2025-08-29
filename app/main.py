from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.routers import demand
from .database import Base, engine
from app.routers import equipment, workshops, workorders
from app import admin, config

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fleet Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=config.settings.SECRET_KEY)

# Routers
app.include_router(equipment.router)
app.include_router(workshops.router)
app.include_router(workorders.router)
app.include_router(demand.router)
# SQLAdmin
admin.setup_admin(app)
