from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import Optional, List

from database import get_db
from models import Device, AlertLog
from schemas import Device as DeviceSchema
from services.hikvision_service import check_single_nvr_async

router = APIRouter(tags=["devices"])

@router.get("/api/devices")
async def get_devices(type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = select(Device)
    if type:
        query = query.where(Device.Type == type)
        
    result = await db.execute(query)
    devices = result.scalars().all()
    
    # We must format with Pydantic to get snake_case properly
    device_schemas = [DeviceSchema.model_validate(d).model_dump() for d in devices]
    
    return {"success": True, "data": device_schemas}

@router.get("/api/devices/{device_id}")
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.Id == device_id))
    device = result.scalars().first()
    
    if not device:
        # C# app returns 404 with success=False JSON
        return {"success": False, "message": "Device not found"}
        
    return {"success": True, "data": DeviceSchema.model_validate(device).model_dump()}

@router.get("/api/dashboard")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device))
    devices = result.scalars().all()
    
    total = len(devices)
    online = sum(1 for d in devices if d.IsOnline == 1)
    offline = sum(1 for d in devices if d.IsOnline == 0)
    nvrCount = sum(1 for d in devices if d.Type == "NVR")
    camCount = sum(1 for d in devices if d.Type == "CAM")
    atmCount = sum(1 for d in devices if d.Type == "ATM")
    crmCount = sum(1 for d in devices if d.Type == "CRM")
    routerCount = sum(1 for d in devices if d.Type == "Router")
    serverCount = sum(1 for d in devices if d.Type == "Server")
    
    critical_alerts = []
    for d in devices:
        is_critical = False
        if d.IsOnline == 0:
            is_critical = True
        elif d.Type == "ATM" and (d.AtmBalance is not None and d.AtmBalance < 500000 or d.AtmStatus != "Normal"):
            is_critical = True
        elif d.Type == "NVR" and d.IsOnline == 1 and d.NvrRecording == 0:
            is_critical = True
            
        if is_critical:
            critical_alerts.append(DeviceSchema.model_validate(d).model_dump())
            
    return {
        "success": True,
        "data": {
            "total": total,
            "online": online,
            "offline": offline,
            "nvrCount": nvrCount,
            "camCount": camCount,
            "atmCount": atmCount,
            "crmCount": crmCount,
            "routerCount": routerCount,
            "serverCount": serverCount,
            "criticalAlerts": critical_alerts
        }
    }

@router.get("/api/devices/{device_id}/ping-history")
async def get_ping_history(device_id: int):
    return {"success": True, "data": []}

from database import AsyncSessionLocal

@router.post("/api/devices/{device_id}/check-nvr")
async def check_nvr(device_id: int):
    result = await check_single_nvr_async(device_id, AsyncSessionLocal)
    return {"success": True, "data": result}


# =============================================================================
# NVR Video Resolution Control Router Endpoints
# =============================================================================
from services.hikvision_service import (
    extract_channel_id,
    get_camera_resolution_async,
    set_camera_resolution_async
)

@router.get("/api/devices/{device_id}/resolution")
async def get_device_resolution(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.Id == device_id))
    cam = result.scalars().first()
    if not cam or cam.Type != "CAM":
        return {"success": False, "message": "Camera device not found"}
        
    if not cam.ParentNvrId:
        return {"success": False, "message": "Camera has no parent NVR"}
        
    nvr_result = await db.execute(select(Device).where(Device.Id == cam.ParentNvrId))
    nvr = nvr_result.scalars().first()
    if not nvr:
        return {"success": False, "message": "Parent NVR not found"}
        
    channel_id = extract_channel_id(cam.Name)
    res = await get_camera_resolution_async(nvr, channel_id, cam.Id)
    return res

@router.post("/api/devices/{device_id}/resolution")
async def set_device_resolution(device_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.Id == device_id))
    cam = result.scalars().first()
    if not cam or cam.Type != "CAM":
        return {"success": False, "message": "Camera device not found"}
        
    if not cam.ParentNvrId:
        return {"success": False, "message": "Camera has no parent NVR"}
        
    nvr_result = await db.execute(select(Device).where(Device.Id == cam.ParentNvrId))
    nvr = nvr_result.scalars().first()
    if not nvr:
        return {"success": False, "message": "Parent NVR not found"}
        
    channel_id = extract_channel_id(cam.Name)
    stream_type = payload.get("stream_type", "main")
    width = payload.get("width")
    height = payload.get("height")
    framerate = payload.get("framerate")
    bitrate = payload.get("bitrate")
    protocol = payload.get("protocol")
    
    if width is None and height is None and framerate is None and bitrate is None and protocol is None:
        return {"success": False, "message": "At least one stream setting parameter (width/height, framerate, bitrate, or protocol) must be specified"}
        
    res = await set_camera_resolution_async(
        nvr, channel_id, cam.Id, stream_type,
        width=width, height=height,
        framerate=framerate, bitrate=bitrate,
        protocol=protocol
    )
    return res

@router.post("/api/devices/nvr/{nvr_id}/batch-resolution")
async def set_nvr_batch_resolution(nvr_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    nvr_result = await db.execute(select(Device).where(Device.Id == nvr_id))
    nvr = nvr_result.scalars().first()
    if not nvr or nvr.Type != "NVR":
        return {"success": False, "message": "NVR device not found"}
        
    width = payload.get("width")
    height = payload.get("height")
    stream_type = payload.get("stream_type", "main")
    
    if not width or not height:
        return {"success": False, "message": "Width and height parameters are required"}
        
    # Get all CAM devices linked to this NVR
    cams_result = await db.execute(select(Device).where(Device.Type == "CAM", Device.ParentNvrId == nvr_id))
    cameras = cams_result.scalars().all()
    
    if not cameras:
        return {"success": True, "message": "No cameras connected to this NVR", "results": []}
        
    import asyncio
    sem = asyncio.Semaphore(3) # Limit concurrency
    
    async def run_set(cam):
        async with sem:
            channel_id = extract_channel_id(cam.Name)
            r = await set_camera_resolution_async(nvr, channel_id, cam.Id, stream_type, width, height)
            return {"cam_id": cam.Id, "cam_name": cam.Name, "success": r.get("success", False), "message": r.get("message")}
            
    tasks = [run_set(cam) for cam in cameras]
    results = await asyncio.gather(*tasks)
    
    overall_success = all(r["success"] for r in results)
    
    return {
        "success": True,
        "overall_success": overall_success,
        "message": "Batch resolution configuration complete",
        "results": results
    }


# =============================================================================
# NVR NTP Clock Synchronization & Time Difference Router Endpoints
# =============================================================================
from models import SystemSettings
from services.hikvision_service import get_nvr_time_async, sync_nvr_time_async

@router.get("/api/devices/{device_id}/nvr-time")
async def get_device_nvr_time(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.Id == device_id))
    nvr = result.scalars().first()
    if not nvr or nvr.Type != "NVR":
        return {"success": False, "message": "NVR device not found"}
        
    settings_result = await db.execute(select(SystemSettings).where(SystemSettings.Id == 1))
    settings = settings_result.scalars().first()
    
    ntp_host = settings.NtpServerIp if settings and settings.NtpServerIp else "10.128.92.9"
    ntp_port = settings.NtpServerPort if settings and settings.NtpServerPort else 123
    
    res = await get_nvr_time_async(nvr, ntp_host, ntp_port)
    return res

@router.post("/api/devices/{device_id}/sync-time")
async def sync_device_nvr_time(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.Id == device_id))
    nvr = result.scalars().first()
    if not nvr or nvr.Type != "NVR":
        return {"success": False, "message": "NVR device not found"}
        
    settings_result = await db.execute(select(SystemSettings).where(SystemSettings.Id == 1))
    settings = settings_result.scalars().first()
    
    ntp_host = settings.NtpServerIp if settings and settings.NtpServerIp else "10.128.92.9"
    ntp_port = settings.NtpServerPort if settings and settings.NtpServerPort else 123
    
    res = await sync_nvr_time_async(nvr, ntp_host, ntp_port)
    return res


# =============================================================================
# NVR Camera Recording Range Router Endpoints
# =============================================================================
from services.hikvision_service import get_camera_recording_range_async

@router.get("/api/devices/{camera_id}/recording-range")
async def get_camera_recording_range(camera_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.Id == camera_id))
    camera = result.scalars().first()
    if not camera or camera.Type != "CAM":
        return {"success": False, "message": "Camera device not found"}
        
    parent_nvr_id = camera.ParentNvrId
    if not parent_nvr_id:
        return {"success": False, "message": "Camera does not have a parent NVR"}
        
    nvr_result = await db.execute(select(Device).where(Device.Id == parent_nvr_id))
    nvr = nvr_result.scalars().first()
    if not nvr or nvr.Type != "NVR":
        return {"success": False, "message": "Parent NVR not found"}
        
    res = await get_camera_recording_range_async(nvr, camera.Name)
    return res


# =============================================================================
# Device CRUD Endpoints (Add, Edit, Delete)
# =============================================================================
from datetime import datetime

@router.post("/api/devices")
async def create_device(payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        now_str = datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
        device = Device(
            Name=payload.get("name", ""),
            Ip=payload.get("ip", ""),
            Type=payload.get("type", ""),
            Location=payload.get("location"),
            Notes=payload.get("notes"),
            HikUsername=payload.get("hik_username"),
            HikPassword=payload.get("hik_password"),
            ParentNvrId=payload.get("parent_nvr_id"),
            IsOnline=1,
            ConsecutiveFailures=0,
            CreatedAt=now_str,
            UpdatedAt=now_str
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return {"success": True, "message": "Device added successfully", "data": DeviceSchema.model_validate(device).model_dump()}
    except Exception as e:
        return {"success": False, "error": f"Failed to add device: {str(e)}"}

@router.put("/api/devices/{device_id}")
async def update_device(device_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Device).where(Device.Id == device_id))
        device = result.scalars().first()
        
        if not device:
            return {"success": False, "error": "Device not found"}
            
        if "name" in payload:
            device.Name = payload["name"]
        if "ip" in payload:
            device.Ip = payload["ip"]
        if "type" in payload:
            device.Type = payload["type"]
        if "location" in payload:
            device.Location = payload["location"]
        if "notes" in payload:
            device.Notes = payload["notes"]
        if "hik_username" in payload:
            device.HikUsername = payload["hik_username"]
        if "hik_password" in payload:
            device.HikPassword = payload["hik_password"]
        if "parent_nvr_id" in payload:
            device.ParentNvrId = payload["parent_nvr_id"]
            
        device.UpdatedAt = datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
        
        await db.commit()
        await db.refresh(device)
        return {"success": True, "message": "Device updated successfully", "data": DeviceSchema.model_validate(device).model_dump()}
    except Exception as e:
        return {"success": False, "error": f"Failed to update device: {str(e)}"}

@router.delete("/api/devices/{device_id}")
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Device).where(Device.Id == device_id))
        device = result.scalars().first()
        
        if not device:
            return {"success": False, "error": "Device not found"}
            
        await db.delete(device)
        await db.commit()
        return {"success": True, "message": "Device deleted successfully"}
    except Exception as e:
        return {"success": False, "error": f"Failed to delete device: {str(e)}"}


# =============================================================================
# NVR Camera Live Streaming Snapshot Endpoint
# =============================================================================
from fastapi import Response
import httpx
import os

@router.get("/api/devices/{camera_id}/snapshot")
async def get_camera_snapshot(camera_id: int, db: AsyncSession = Depends(get_db)):
    try:
        # 1. Fetch camera
        result = await db.execute(select(Device).where(Device.Id == camera_id))
        camera = result.scalars().first()
        if not camera or camera.Type != "CAM":
            return Response(status_code=404, content=b"Camera not found")
            
        # 2. Fetch parent NVR
        parent_nvr_id = camera.ParentNvrId
        if not parent_nvr_id:
            return Response(status_code=404, content=b"Camera does not have parent NVR")
            
        nvr_result = await db.execute(select(Device).where(Device.Id == parent_nvr_id))
        nvr = nvr_result.scalars().first()
        if not nvr:
            return Response(status_code=404, content=b"Parent NVR not found")
            
        # 3. Check if parent NVR is offline or simulated
        if not nvr.IsOnline or not nvr.Ip or not nvr.HikUsername or not nvr.HikPassword:
            # Serve mock placeholder image
            mock_img_path = "wwwroot/img/camera_placeholder.png"
            if os.path.exists(mock_img_path):
                with open(mock_img_path, "rb") as f:
                    return Response(content=f.read(), media_type="image/png")
            else:
                return Response(status_code=404, content=b"NVR offline and no mock placeholder image found")
                
        # 4. Construct NVR credentials & channel ID
        channel_id = extract_channel_id(camera.Name)
        if not channel_id:
            return Response(status_code=400, content=b"Could not extract camera channel ID")
            
        # Channel mainstream image track = channel_id * 100 + 1 (e.g. 101, 201)
        track_id = channel_id * 100 + 1
        url = f"http://{nvr.Ip}/ISAPI/Streaming/channels/{track_id}/picture"
        auth = httpx.DigestAuth(nvr.HikUsername, nvr.HikPassword)
        
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(url, auth=auth)
            if res.status_code == 200 and res.content:
                return Response(content=res.content, media_type="image/jpeg")
            else:
                # Fallback to sub-channel if mainstream failed
                sub_track = channel_id * 100 + 2
                url_sub = f"http://{nvr.Ip}/ISAPI/Streaming/channels/{sub_track}/picture"
                res_sub = await client.get(url_sub, auth=auth)
                if res_sub.status_code == 200 and res_sub.content:
                    return Response(content=res_sub.content, media_type="image/jpeg")
                else:
                    return Response(status_code=res.status_code, content=b"NVR snapshot query failed")
    except Exception as e:
        return Response(status_code=500, content=f"Error: {str(e)}".encode())



