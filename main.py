import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import engine
from models import Base
# Asigură-te că 'printing' este importat în această listă
from routes import (
    store_categories, printing, logs, orders, sync,
    labels, settings, validation, webhooks, couriers
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    print("Aplicația pornește... crearea tabelelor în baza de date.")
    await init_db()
    print("Tabelele au fost create cu succes.")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Aici activăm toate "departamentele" ---
app.include_router(orders.router, tags=["orders"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
app.include_router(logs.router, prefix="/logs", tags=["logs"])
app.include_router(sync.router, prefix="/sync", tags=["sync"])
app.include_router(labels.router, prefix="/labels", tags=["labels"])
app.include_router(validation.router, prefix="/validation", tags=["validation"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(couriers.router, prefix="/couriers", tags=["couriers"])
app.include_router(store_categories.router, prefix="/store_categories", tags=["store_categories"])

# --- ACEASTA ESTE LINIA CARE LIPSEA ---
# Acum, aplicația știe și de rutele definite în routes/printing.py
app.include_router(printing.router, prefix="/print", tags=["printing"])
# ------------------------------------