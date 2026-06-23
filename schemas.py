from datetime import datetime
from typing import Optional, List, Annotated
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, EmailStr, Field, BeforeValidator

IntAsString = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else None)]

# Request Schemas

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


class LikeRequest(BaseModel):
    target_id: int
    target_type: str = Field(..., description="Must be 'post', 'comment', 'reel', or 'story'")


# Response Schemas

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

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# Social Graph Schemas

class FollowResponse(BaseModel):
    follower_id: IntAsString
    following_id: IntAsString
    followed_at: datetime

    class Config:
        from_attributes = True


class FollowRequestResponse(BaseModel):
    request_id: IntAsString
    sender_id: IntAsString
    receiver_id: IntAsString
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# Content Management Schemas

class PostCreateRequest(BaseModel):
    caption: Optional[str] = None
    location: Optional[str] = None
    visibility: str = Field("public", description="e.g., 'public', 'private', 'close_friends'")


class PostResponse(BaseModel):
    post_id: IntAsString
    profile_id: IntAsString
    caption: Optional[str] = None
    location: Optional[str] = None
    visibility: str
    created_at: datetime

    class Config:
        from_attributes = True


class CommentCreateRequest(BaseModel):
    comment_text: str = Field(..., min_length=1)


class CommentResponse(BaseModel):
    comment_id: IntAsString
    post_id: IntAsString
    profile_id: IntAsString
    comment_text: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReelCreateRequest(BaseModel):
    caption: Optional[str] = None
    duration: int = Field(..., description="Duration in seconds")


class ReelResponse(BaseModel):
    reel_id: IntAsString
    profile_id: IntAsString
    caption: Optional[str] = None
    duration: int
    created_at: datetime

    class Config:
        from_attributes = True


class StoryResponse(BaseModel):
    story_id: IntAsString
    profile_id: IntAsString
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True

# Direct Messaging Schemas

class ConversationResponse(BaseModel):
    conversation_id: IntAsString
    conversation_type: str
    created_at: datetime
    name: Optional[str] = None
    recipient_username: Optional[str] = None
    recipient_avatar: Optional[str] = None
    last_message: Optional[str] = None
    member_usernames: Optional[List[str]] = None

    class Config:
        from_attributes = True


class GroupConversationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    member_usernames: List[str]


class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    message_type: str = Field("text", description="e.g., 'text', 'image', 'video'")


class MessageResponse(BaseModel):
    message_id: IntAsString
    conversation_id: IntAsString
    sender_id: IntAsString
    message_type: str
    content: str
    sent_at: datetime
    sender_username: Optional[str] = None
    sender_avatar: Optional[str] = None

    class Config:
        from_attributes = True


class ReactionRequest(BaseModel):
    emoji: str = Field(..., description="The reaction emoji")
