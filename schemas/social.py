from datetime import datetime
from typing import Annotated
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, BeforeValidator

IntAsString = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else None)]

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
