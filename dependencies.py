# pyrefly: ignore [missing-import]
from fastapi import Depends, HTTPException, status, WebSocket
# pyrefly: ignore [missing-import]
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from database import get_db, models
from crud import crud_sql

security = HTTPBearer()


import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, WebSocket] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, profile_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[profile_id] = websocket
        self.loop = asyncio.get_running_loop()

    def disconnect(self, profile_id: int):
        if profile_id in self.active_connections:
            del self.active_connections[profile_id]

    async def send_personal_message(self, message: dict, profile_id: int):
        if profile_id in self.active_connections:
            try:
                await self.active_connections[profile_id].send_json(message)
            except Exception:
                # Handle disconnected socket gracefully
                self.disconnect(profile_id)

    def send_personal_message_sync(self, message: dict, profile_id: int):
        if profile_id in self.active_connections and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.send_personal_message(message, profile_id),
                self.loop
            )

    async def broadcast_notification(self, notification_data: dict, profile_id: int):
        if profile_id in self.active_connections:
            try:
                await self.active_connections[profile_id].send_json({
                    "type": "notification",
                    "data": notification_data
                })
            except Exception:
                self.disconnect(profile_id)

    def broadcast_notification_sync(self, notification_data: dict, profile_id: int):
        if profile_id in self.active_connections and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_notification(notification_data, profile_id),
                self.loop
            )


ws_manager = ConnectionManager()



def get_current_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> models.Profile:
    token_str = credentials.credentials
    profile = crud_sql.authenticate_access_token(db, token_str)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if profile.user.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your user account is suspended."
        )
    return profile


def get_current_admin(
    profile: models.Profile = Depends(get_current_profile)
) -> models.Profile:
    if profile.account_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required"
        )
    return profile
