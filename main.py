# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/main.py

from fastapi import FastAPI, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import models
from database import engine, get_db
from dependencies import get_templates
from routes import store_categories, printing, logs, orders, sync, labels, settings, validation, webhooks, couriers
from websocket_manager import manager

# --- START MODIFICARE ---
# Am mutat crearea tabelelor într-o funcție asincronă
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

app = FastAPI()
app.state.is_syncing = False


@app.on_event("startup")
async def on_startup():
    await create_tables()
# --- FINAL MODIFICARE ---

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, templates = Depends(get_templates)):
    return templates.TemplateResponse("index.html", {"request": request})

# Include all the routers from the routes directory
app.include_router(orders.router)
app.include_router(settings.router)
app.include_router(store_categories.router)
app.include_router(printing.router)
app.include_router(sync.router)
app.include_router(logs.router)
app.include_router(labels.router)
app.include_router(validation.router)
app.include_router(webhooks.router)
app.include_router(couriers.router)

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)