import os
import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import Device, AlertLog, User, SystemSettings

async def seed_database_if_empty(db: AsyncSession):
    # Check if we have any devices
    result = await db.execute(select(Device).limit(1))
    if result.scalars().first():
        return # Already seeded
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "database", "monitor-data.json")
    if not os.path.exists(json_path):
        json_path = os.path.join(base_dir, "monitor-data.json")
        
    if not os.path.exists(json_path):
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    is_mssql = db.bind.dialect.name == "mssql"
    
    # 1. Seed Devices
    devices = data.get("devices", [])
    if devices:
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT Devices ON"))
        for d in devices:
            device = Device(
                Id = d.get("id"),
                Name = d.get("name", ""),
                Ip = d.get("ip", ""),
                Type = d.get("type", ""),
                Location = d.get("location"),
                HikUsername = d.get("hik_username"),
                HikPassword = d.get("hik_password"),
                Notes = d.get("notes"),
                ParentNvrId = d.get("parent_nvr_id"),
                IsOnline = d.get("is_online", 1),
                LastPingTime = d.get("last_ping_time"),
                LastLatency = d.get("last_latency"),
                LastPacketLoss = d.get("last_packet_loss"),
                ConsecutiveFailures = d.get("consecutive_failures", 0),
                DownSince = d.get("down_since"),
                EmailAlertSent = d.get("email_alert_sent", 0),
                SmsAlertSent = d.get("sms_alert_sent", 0),
                NvrRecording = d.get("nvr_recording") or 0,
                NvrLastRecordingDate = d.get("nvr_last_recording_date"),
                NvrHddStatus = d.get("nvr_hdd_status"),
                AtmBalance = d.get("atm_balance"),
                AtmStatus = d.get("atm_status"),
                AtmLastUpdated = d.get("atm_last_updated"),
                CreatedAt = d.get("created_at"),
                UpdatedAt = d.get("updated_at")
            )
            db.add(device)
        await db.flush()
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT Devices OFF"))
        
    # 2. Seed Alerts
    alerts = data.get("alerts", [])
    if alerts:
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT AlertLogs ON"))
        for a in alerts:
            alert = AlertLog(
                Id = a.get("id"),
                DeviceId = a.get("device_id"),
                AlertType = a.get("alert_type", ""),
                Message = a.get("message", ""),
                Recipients = a.get("recipients"),
                SentAt = a.get("sent_at"),
                Success = a.get("success", 0)
            )
            db.add(alert)
        await db.flush()
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT AlertLogs OFF"))
        
    # 3. Seed Users
    users = data.get("users", [])
    if users:
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT Users ON"))
        for u in users:
            user = User(
                Id = u.get("id"),
                Username = u.get("username", ""),
                PasswordHash = u.get("password_hash", ""),
                Role = u.get("role", ""),
                CreatedAt = u.get("created_at")
            )
            db.add(user)
        await db.flush()
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT Users OFF"))
        
    # 4. Seed Settings
    settings_data = data.get("settings")
    if settings_data:
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT SystemSettings ON"))
        setting = SystemSettings(
            Id = 1,
            SmtpHost = settings_data.get("smtp_host"),
            SmtpPort = settings_data.get("smtp_port"),
            SmtpUser = settings_data.get("smtp_user"),
            SmtpPass = settings_data.get("smtp_pass"),
            SmtpFrom = settings_data.get("smtp_from"),
            SmtpSecure = settings_data.get("smtp_secure"),
            EmailRecipients = settings_data.get("email_recipients"),
            SmsApiUrl = settings_data.get("sms_api_url"),
            SmsApiMethod = settings_data.get("sms_api_method"),
            SmsApiHeaders = settings_data.get("sms_api_headers"),
            SmsApiBodyTemplate = settings_data.get("sms_api_body_template"),
            SmsRecipients = settings_data.get("sms_recipients"),
            PingIntervalMinutes = settings_data.get("ping_interval_minutes"),
            NvrCheckIntervalMinutes = settings_data.get("nvr_check_interval_minutes"),
            EmailAlertAfterMinutes = settings_data.get("email_alert_after_minutes"),
            SmsAlertAfterMinutes = settings_data.get("sms_alert_after_minutes"),
            AtmApiKey = settings_data.get("atm_api_key")
        )
        db.add(setting)
        await db.flush()
        if is_mssql:
            await db.execute(text("SET IDENTITY_INSERT SystemSettings OFF"))
        
    await db.commit()
