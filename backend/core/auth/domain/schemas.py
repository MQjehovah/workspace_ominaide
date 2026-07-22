from datetime import datetime
from pydantic import BaseModel, EmailStr


class ContactInfo(BaseModel):
    name: str
    relation: str | None = None


class ProjectInfo(BaseModel):
    name: str
    deadline: str | None = None


class UserProfileResponse(BaseModel):
    user_id: int
    name: str | None = None
    role: str | None = None
    company: str | None = None
    contacts: list[ContactInfo] | None = None
    projects: list[ProjectInfo] | None = None
    preferences: dict | None = None
    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    company: str | None = None
    contacts: list[ContactInfo] | None = None
    projects: list[ProjectInfo] | None = None
    preferences: dict | None = None


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


class AdminUserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ToggleActiveRequest(BaseModel):
    is_active: bool


class UpdateUserRequest(BaseModel):
    username: str | None = None
    email: str | None = None
