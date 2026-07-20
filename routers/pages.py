from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")

@router.get("/")
async def dashboard_home(request: Request):
    # Renders the dashboard shell (Phase 1)
    return templates.TemplateResponse("dashboard/index.html", {"request": request})
