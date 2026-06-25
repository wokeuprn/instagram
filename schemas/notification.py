from typing import Annotated, Optional
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, BeforeValidator

IntAsString = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else None)]

class NotificationResponse(BaseModel):
    notification_id: IntAsString
    receiver_id: IntAsString
    user_id: IntAsString  # Sender/Actor Profile ID
    notification_type: str
    reference_id: IntAsString
    is_read: bool
    actor_username: Optional[str] = None
    actor_avatar: Optional[str] = None
    content: Optional[str] = None

    class Config:
        from_attributes = True

