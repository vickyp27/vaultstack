import os, jwt, datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

router  = APIRouter(prefix="/api/auth", tags=["auth"])
bearer  = HTTPBearer(auto_error=False)

SECRET   = os.getenv("PORTAL_SECRET", "vaultstack-secret-key-change-in-prod")
USERNAME = os.getenv("PORTAL_USERNAME", "vaultadmin")
PASSWORD = os.getenv("PORTAL_PASSWORD", "VaultStack@2025")
ALGO     = "HS256"

class LoginRequest(BaseModel):
    username: str
    password: str

def make_token() -> str:
    payload = {
        "sub": USERNAME,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=12),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def verify_token(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=[ALGO])
        return data["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/login")
def login(body: LoginRequest):
    if body.username != USERNAME or body.password != PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": make_token(), "username": USERNAME}

@router.get("/me")
def me(user: str = Depends(verify_token)):
    return {"username": user}
