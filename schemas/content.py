from datetime import datetime
from typing import Optional, Annotated, List
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, BeforeValidator

IntAsString = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else None)]

class LikeRequest(BaseModel):
    target_id: int
    target_type: str = Field(..., description="Must be 'post', 'comment', 'reel', or 'story'")


class PostCreateRequest(BaseModel):
    caption: Optional[str] = None
    location: Optional[str] = None
    visibility: str = Field("public", description="e.g., 'public', 'private', 'close_friends'")
    media_url: Optional[str] = None


class PostResponse(BaseModel):
    post_id: IntAsString
    profile_id: IntAsString
    caption: Optional[str] = None
    location: Optional[str] = None
    visibility: str
    media_url: Optional[str] = None
    created_at: datetime
    username: Optional[str] = None
    profile_picture: Optional[str] = None

    class Config:
        from_attributes = True


class CommentCreateRequest(BaseModel):
    comment_text: str = Field(..., min_length=1)


class CommentResponse(BaseModel):
    comment_id: IntAsString
    post_id: IntAsString
    profile_id: IntAsString
    parent_comment_id: Optional[IntAsString] = None
    comment_text: str
    username: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: datetime
    replies: Optional[List["CommentResponse"]] = []

    class Config:
        from_attributes = True

CommentResponse.model_rebuild()


class ReelCreateRequest(BaseModel):
    caption: Optional[str] = None
    duration: int = Field(..., description="Duration in seconds")
    media_url: Optional[str] = None


class ReelResponse(BaseModel):
    reel_id: IntAsString
    profile_id: IntAsString
    caption: Optional[str] = None
    duration: int
    media_url: Optional[str] = None
    created_at: datetime
    username: Optional[str] = None
    profile_picture: Optional[str] = None

    class Config:
        from_attributes = True


class StoryCreateRequest(BaseModel):
    media_url: Optional[str] = None


class StoryResponse(BaseModel):
    story_id: IntAsString
    profile_id: IntAsString
    media_url: Optional[str] = None
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class ReelCommentResponse(BaseModel):
    reel_comment_id: IntAsString
    reel_id: IntAsString
    profile_id: IntAsString
    comment_text: str
    username: Optional[str] = None
    profile_picture: Optional[str] = None

    class Config:
        from_attributes = True

