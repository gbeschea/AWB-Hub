# routes/settings.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dependencies import get_templates

router = APIRouter(tags=['Settings'])

@router.get("/settings", response_class=HTMLResponse, name="get_settings_page")
async def get_settings_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Afișează pagina principală de setări."""
    return templates.TemplateResponse("settings.html", {"request": request})