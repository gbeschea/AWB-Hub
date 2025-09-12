import logging
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import models
from database import engine
# NOU: Adaugă 'validation' la lista de importuri
from routes import store_categories, courier_categories, printing, logs, orders, sync, labels, settings, validation
from routes import webhooks

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI(title='AWB Hub')
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

app.state.is_syncing = False

app.include_router(orders.router)
app.include_router(store_categories.router)
app.include_router(courier_categories.router)
app.include_router(printing.router)
app.include_router(logs.router)
app.include_router(sync.router)
app.include_router(labels.router)
app.include_router(settings.router)
# NOU: Adaugă router-ul pentru pagina de validare
app.include_router(validation.router)
app.include_router(webhooks.router)


@app.get("/", response_class=RedirectResponse, include_in_schema=False, tags=['Root'])
def home(request: Request):
    return RedirectResponse(url=request.url_for('view_orders'))