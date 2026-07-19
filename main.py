import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import socketio

from database import engine, Base, AsyncSessionLocal
from seeder import seed_database_if_empty
from routers import auth, devices, alerts, settings
from services.ping_service import background_ping_check
from services.hikvision_service import background_hikvision_check


sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as db:
        await seed_database_if_empty(db)
        
    ping_task = asyncio.create_task(background_ping_check(AsyncSessionLocal))
    hikvision_task = asyncio.create_task(background_hikvision_check(AsyncSessionLocal))
    
    yield
    
    # Shutdown
    ping_task.cancel()
    hikvision_task.cancel()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(alerts.router)
app.include_router(settings.router)


# Mount static files (wwwroot)
app.mount("/", StaticFiles(directory="wwwroot", html=True), name="wwwroot")

# Wrap FastAPI with Socket.IO ASGIApp
app = socketio.ASGIApp(sio, other_asgi_app=app)

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

# SignalR expects a different protocol usually, but the frontend connects to /socket.io
# If the frontend uses Socket.IO client, this will work out of the box.
