# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field

class UserStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Must be 'active' or 'suspended'")


class ProfileVerificationRequest(BaseModel):
    verified_status: bool


class AdminStatsResponse(BaseModel):
    total_users: int
    total_profiles: int
    total_posts: int
    total_reels: int
    total_comments: int
