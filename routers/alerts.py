from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from typing import Optional

from database import get_db
from models import AlertLog
from schemas import AlertLog as AlertLogSchema

router = APIRouter(tags=["alerts"])

@router.get("/api/alerts/recent")
async def get_recent_alerts(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AlertLog).order_by(AlertLog.Id.desc()).limit(limit))
    alerts = result.scalars().all()
    
    alert_schemas = [AlertLogSchema.model_validate(a).model_dump() for a in alerts]
    
    return {"success": True, "data": alert_schemas}

@router.post("/api/alerts/clear")
async def clear_alerts(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(AlertLog))
    await db.commit()
    return {"success": True, "message": "Alert logs cleared"}
