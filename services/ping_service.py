import asyncio
import re
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import Device

PORTS_TO_TRY = [80, 8000, 443, 554, 23]

async def tcp_probe_wrapper(ip: str, port: int) -> bool:
    try:
        fut = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(fut, timeout=2.0)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

async def run_ping_cmd(ip: str) -> tuple[bool, int, int]:
    try:
        cmd = f"ping.exe -n 4 -w 1000 {ip}"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode('ansi', errors='ignore')
        
        # Parse packet loss percentage
        loss_match = re.search(r'(\d+)% loss', out, re.IGNORECASE)
        loss = int(loss_match.group(1)) if loss_match else 100
        
        # Parse average latency
        avg_match = re.search(r'Average = (\d+)ms', out, re.IGNORECASE)
        latency = int(avg_match.group(1)) if avg_match else None
        
        is_online = loss < 100
        
        if latency is None and is_online:
            times = re.findall(r'time[=<](\d+)ms', out, re.IGNORECASE)
            if times:
                latency = int(times[0])
            else:
                latency = 5
                
        return is_online, latency, loss
    except Exception as e:
        print(f"System ping failed for {ip}: {e}")
        return False, None, 100

async def ping_device_async(device_id: int, session_maker):
    async with session_maker() as db:
        device = await db.get(Device, device_id)
        if not device or not device.Ip:
            return
        ip = device.Ip
        current_online = device.IsOnline
        consecutive_failures = device.ConsecutiveFailures

    is_online, latency, loss = await run_ping_cmd(ip)
    
    # Fallback to TCP port probe if ICMP ping failed/blocked
    if not is_online:
        for port in PORTS_TO_TRY:
            if await tcp_probe_wrapper(ip, port):
                is_online = True
                latency = 5
                loss = 0
                break
                
    now_str = datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
    
    async with session_maker() as db:
        device = await db.get(Device, device_id)
        if not device:
            return
            
        if is_online:
            device.IsOnline = 1
            device.LastLatency = latency
            device.LastPacketLoss = loss
            device.ConsecutiveFailures = 0
            device.DownSince = None
        else:
            if current_online == 1:
                device.DownSince = now_str
            device.IsOnline = 0
            device.LastPacketLoss = 100
            device.LastLatency = None
            device.ConsecutiveFailures = consecutive_failures + 1
            
        device.LastPingTime = now_str
        device.UpdatedAt = now_str
        await db.commit()

async def background_ping_check(session_maker):
    while True:
        try:
            async with session_maker() as db:
                result = await db.execute(select(Device.Id))
                device_ids = result.scalars().all()
                
            sem = asyncio.Semaphore(20)
            
            async def bounded_ping(d_id):
                async with sem:
                    await ping_device_async(d_id, session_maker)
                        
            tasks = [bounded_ping(d_id) for d_id in device_ids]
            await asyncio.gather(*tasks)
            
        except Exception as e:
            print(f"Error in background_ping_check: {e}")
            
        await asyncio.sleep(60) # check every minute
