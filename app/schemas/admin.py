from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    source: Optional[str] = Field(None, max_length=20)
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class UserBaseAdmin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class UserCreateAdmin(UserBaseAdmin):
    password: str = Field(..., min_length=8, max_length=128)
    role: str = "user"
    is_active: bool = True
    source: str = "local"


class UserUpdateAdmin(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    role: Optional[str] = Field(None, max_length=50)


class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


class UserToggleActive(BaseModel):
    is_active: bool


class RoleAssignRequest(BaseModel):
    role_id: int


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_system: bool
    is_active: bool


class UserRoleAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    role_id: int
    role: RoleResponse
    assigned_by: Optional[int] = None
    created_at: datetime


class UserWithRolesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    role: str
    source: str
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    roles: List[RoleResponse] = []


class UserListResponse(BaseModel):
    users: List[UserWithRolesResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class MessageResponse(BaseModel):
    message: str


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    module: Optional[str] = None
    is_system: bool


class GroupBase(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    user_count: int = 0
    role_count: int = 0


class GroupListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class GroupListResponse(BaseModel):
    groups: List[GroupResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class GroupUserAssign(BaseModel):
    user_id: int


class GroupRoleAssign(BaseModel):
    role_id: int


class GroupWithDetailsResponse(GroupResponse):
    users: List[UserWithRolesResponse] = []
    roles: List[RoleResponse] = []


class RoleCreate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_system: bool = False


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    permissions: List[PermissionResponse] = []


class RoleListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    is_system: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class RoleListResponse(BaseModel):
    roles: List[RoleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RolePermissionAssign(BaseModel):
    permission_id: int


class RoleWithPermissionsResponse(RoleResponse):
    pass


class PermissionCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    module: Optional[str] = Field(None, max_length=50)
    is_system: bool = False


class PermissionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    module: Optional[str] = Field(None, max_length=50)


class PermissionListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    module: Optional[str] = Field(None, max_length=50)
    is_system: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class PermissionListResponse(BaseModel):
    permissions: List[PermissionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int