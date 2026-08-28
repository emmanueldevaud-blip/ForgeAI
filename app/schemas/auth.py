from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class TokenBase(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class Token(TokenBase):
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    sub: str
    user_id: int
    role: str
    exp: int


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserCreateAdmin(UserCreate):
    is_admin: bool = False
    role: str = "user"


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    role: Optional[str] = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_admin: bool
    role: str
    source: str
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: UserResponse
    tokens: Token


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class ADSettingsBase(BaseModel):
    ad_enabled: bool = False
    ad_server: str = Field("", max_length=255)
    ad_port: int = Field(636, ge=1, le=65535)
    ad_use_ssl: bool = True
    ad_base_dn: str = Field("", max_length=500)
    ad_user_dn: str = Field("", max_length=500)
    ad_user_search_filter: str = Field("(sAMAccountName={username})", max_length=255)
    ad_group_search_base: str = Field("", max_length=500)
    ad_admin_group: str = Field("", max_length=255)
    ad_bind_user: str = Field("", max_length=255)
    ad_bind_password: str = Field("", max_length=255)
    ad_connect_timeout: int = Field(10, ge=1, le=60)
    ad_receive_timeout: int = Field(10, ge=1, le=60)


class ADSettingsResponse(ADSettingsBase):
    model_config = ConfigDict(from_attributes=True)

    ad_bind_password: str = ""


class ADSettingsUpdate(BaseModel):
    ad_enabled: Optional[bool] = None
    ad_server: Optional[str] = Field(None, max_length=255)
    ad_port: Optional[int] = Field(None, ge=1, le=65535)
    ad_use_ssl: Optional[bool] = None
    ad_base_dn: Optional[str] = Field(None, max_length=500)
    ad_user_dn: Optional[str] = Field(None, max_length=500)
    ad_user_search_filter: Optional[str] = Field(None, max_length=255)
    ad_group_search_base: Optional[str] = Field(None, max_length=500)
    ad_admin_group: Optional[str] = Field(None, max_length=255)
    ad_bind_user: Optional[str] = Field(None, max_length=255)
    ad_bind_password: Optional[str] = Field(None, max_length=255)
    ad_connect_timeout: Optional[int] = Field(None, ge=1, le=60)
    ad_receive_timeout: Optional[int] = Field(None, ge=1, le=60)


class ADTestRequest(BaseModel):
    ad_server: str = Field(..., max_length=255)
    ad_port: int = Field(..., ge=1, le=65535)
    ad_use_ssl: bool = True
    ad_base_dn: str = Field(..., max_length=500)
    ad_bind_user: str = Field(..., max_length=255)
    ad_bind_password: str = Field(..., max_length=255)
    ad_connect_timeout: int = Field(10, ge=1, le=60)
    ad_receive_timeout: int = Field(10, ge=1, le=60)


class ADTestResponse(BaseModel):
    success: bool
    message: str
    details: Optional[str] = None