from datetime import datetime
from typing import Optional, List, Annotated
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, BeforeValidator

IntAsString = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else None)]

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


class AddGroupMembersRequest(BaseModel):
    usernames: List[str]

