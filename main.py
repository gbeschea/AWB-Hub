# main.py
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import models
from database import engine
# DO NOT import get_templates from dependencies, it's no longer needed here
from routes import store_categories, printing, logs, orders, sync, labels, settings, validation, webhooks, couriers
from websocket_manager import manager
from background import start_background_tasks
from settings import settings

# Create all database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add session middleware for flash messages
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Mount the static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include all the different routes from other files
app.include_router(orders.router, tags=["orders"])
app.include_router(sync.router, prefix="/sync", tags=["sync"])
app.include_router(labels.router, prefix="/labels", tags=["labels"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
app.include_router(validation.router, prefix="/validation", tags=["validation"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(couriers.router, prefix="/couriers", tags=["couriers"])
app.include_router(printing.router, prefix="/printing", tags=["printing"])
app.include_router(logs.router, prefix="/logs", tags=["logs"])
app.include_router(store_categories.router, prefix="/categories", tags=["store_categories"])


@app.on_event("startup")
async def startup_event():
    """
    Start background tasks when the application starts.
    """
    start_background_tasks()


@app.websocket("/ws/status")
async def websocket_endpoint(websocket: Request):
    """
    Handles the websocket connection for real-time status updates.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except Exception:
        manager.disconnect(websocket)