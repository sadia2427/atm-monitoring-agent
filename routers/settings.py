from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from database import get_db
from models import SystemSettings
from schemas import SystemSettings as SystemSettingsSchema

router = APIRouter(prefix="/api/settings", tags=["settings"])

@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemSettings).where(SystemSettings.Id == 1))
    setting = result.scalars().first()
    
    if not setting:
        # Create default settings
        setting = SystemSettings(
            Id=1,
            SmtpHost="",
            SmtpPort="",
            SmtpUser="",
            SmtpPass="",
            SmtpFrom="",
            SmtpSecure="0",
            EmailRecipients="",
            SmsApiUrl="",
            SmsApiMethod="POST",
            SmsApiHeaders="",
            SmsApiBodyTemplate="",
            SmsRecipients="",
            PingIntervalMinutes="5",
            NvrCheckIntervalMinutes="15",
            EmailAlertAfterMinutes="60",
            SmsAlertAfterMinutes="120",
            AtmApiKey="",
            NtpServerIp="10.128.92.9",
            NtpServerPort=123
        )
        db.add(setting)
        await db.commit()
        await db.refresh(setting)
        
    return {"success": True, "data": SystemSettingsSchema.model_validate(setting).model_dump()}

@router.post("")
async def save_settings(settings_data: SystemSettingsSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemSettings).where(SystemSettings.Id == 1))
    setting = result.scalars().first()
    
    if not setting:
        setting = SystemSettings(Id=1)
        db.add(setting)
        
    # Update fields
    setting.SmtpHost = settings_data.SmtpHost
    setting.SmtpPort = settings_data.SmtpPort
    setting.SmtpUser = settings_data.SmtpUser
    if settings_data.SmtpPass: # Only update password if provided
        setting.SmtpPass = settings_data.SmtpPass
    setting.SmtpFrom = settings_data.SmtpFrom
    setting.SmtpSecure = settings_data.SmtpSecure
    setting.EmailRecipients = settings_data.EmailRecipients
    setting.SmsApiUrl = settings_data.SmsApiUrl
    setting.SmsApiMethod = settings_data.SmsApiMethod
    setting.SmsApiHeaders = settings_data.SmsApiHeaders
    setting.SmsApiBodyTemplate = settings_data.SmsApiBodyTemplate
    setting.SmsRecipients = settings_data.SmsRecipients
    setting.PingIntervalMinutes = settings_data.PingIntervalMinutes
    setting.NvrCheckIntervalMinutes = settings_data.NvrCheckIntervalMinutes
    setting.EmailAlertAfterMinutes = settings_data.EmailAlertAfterMinutes
    setting.SmsAlertAfterMinutes = settings_data.SmsAlertAfterMinutes
    setting.AtmApiKey = settings_data.AtmApiKey
    setting.NtpServerIp = settings_data.NtpServerIp
    setting.NtpServerPort = settings_data.NtpServerPort
    
    await db.commit()
    return {"success": True, "message": "Settings saved successfully"}
