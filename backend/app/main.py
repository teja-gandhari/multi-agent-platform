
from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.auth import auth_router
from app.api.v1.projects import project_router
from app.database.database import Base, engine


app=FastAPI()

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(project_router)




