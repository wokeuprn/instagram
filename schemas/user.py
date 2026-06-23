from typing import Optional, Annotated
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, EmailStr, Field, BeforeValidator

IntAsString = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else None)]

class UserRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=6)


class UserLoginRequest(BaseModel):
    username_or_email: str
    password: str


class ProfileEditRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    username: Optional[str] = Field(None, min_length=3, max_length=30)
    profile_picture: Optional[str] = None


class UserResponse(BaseModel):
    user_id: IntAsString
    email: str
    full_name: Optional[str]
    is_email_verified: bool
    is_phone_verified: bool

    class Config:
        from_attributes = True


class ProfileResponse(BaseModel):
    profile_id: IntAsString
    user_id: IntAsString
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    profile_picture: Optional[str] = None
    account_type: str
    verified_status: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
