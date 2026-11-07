from fastapi import FastAPI

from app.api import auth, health, resources
from app.core.exceptions import register_exception_handlers

app = FastAPI(title="Reservation API", version="0.1.0")

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(resources.router)
