from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field
from typing import Annotated

router = APIRouter(
  prefix="/users",
  tags=["users"]
)

class UserCreate(BaseModel):
  fullname: Annotated[str, Field(min_length=3)]
  username: Annotated[str, Field(min_length=3)]
  description: str | None
  email: EmailStr
  phone: str | None
  password: Annotated[str, Field(min_length=8)]

class UserUpdate(BaseModel):
  fullname: Annotated[str | None, Field(min_length=3)]
  username: Annotated[str | None, Field(min_length=3)]
  description: str | None
  email: EmailStr | None
  phone: str | None

@router.get("/")
async def getAllUsers():
  return "All users"

@router.get("/{user_id}")
async def getUser(user_id: str):
  return f"User with id {user_id}"

@router.post("/")
async def createUser(user: UserCreate):
  return user

@router.put("/{user_id}")
async def updateUser(user_id: str, user: UserUpdate):
  return {user_id, user}

@router.delete("/{user_id}")
async def deleteUser(user_id: str):
  return f"User with ID {user_id} was deleted"