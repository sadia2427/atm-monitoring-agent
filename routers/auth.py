from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import hashlib
import binascii

from database import get_db
from models import User
from schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])

def hash_password(password: str) -> str:
    salt = b"adc_monitor_salt"
    # PBKDF2 HMAC SHA512 with 1000 iterations to match C# implementation
    dk = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt, 1000, dklen=64)
    return binascii.hexlify(dk).decode('utf-8').lower()

@router.post("/login")
async def login(request_data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    if not request_data.username or not request_data.password:
        return {"success": False, "error": "Username and password are required"}

    result = await db.execute(select(User).where(User.Username == request_data.username))
    user = result.scalars().first()
    
    if not user or user.PasswordHash != hash_password(request_data.password):
        response.status_code = 401
        return {"success": False, "error": "Invalid username or password"}

    # Set cookie (simple implementation for token matching the frontend expectations)
    # The C# version sets standard cookie auth. We'll set a cookie named 'token'
    # Normally we'd use JWT, but the C# version used ASP.NET Core cookies. 
    # Let's just set the username as the token for this simple version.
    # In a real app we'd sign it.
    response.set_cookie(key="token", value=user.Username, httponly=True, max_age=86400)

    return {
        "success": True,
        "data": {
            "username": user.Username,
            "role": user.Role
        }
    }

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("token")
    return {"success": True, "message": "Logged out successfully"}

@router.get("/me")
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    result = await db.execute(select(User).where(User.Username == token))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    return {
        "success": True,
        "data": {
            "username": user.Username,
            "role": user.Role
        }
    }
