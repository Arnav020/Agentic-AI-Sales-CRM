from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from backend.db.mongo import create_user_in_db, verify_user_credentials

router = APIRouter()

class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/signup")
def signup(user: SignupRequest):
    result = create_user_in_db(user.username, user.email, user.password)
    if not result:
        raise HTTPException(status_code=400, detail="Username already exists.")
    return {"message": "User created successfully", "username": user.username}


@router.post("/login")
def login(creds: LoginRequest):
    user = verify_user_credentials(creds.username, creds.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"message": "Login successful", "user_id": creds.username, "email": user["email"]}
