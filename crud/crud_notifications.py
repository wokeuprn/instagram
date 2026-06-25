import os
import sys
import secrets
from typing import List, Optional

# Add project root to sys.path to allow direct execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from database import models

# Import ws_manager inside functions to avoid circular import issues if any
def get_ws_manager():
    from dependencies import ws_manager
    return ws_manager


def create_notification(
    db: Session,
    receiver_id: int,
    sender_profile_id: int,
    notification_type: str,
    reference_id: int
) -> Optional[models.Notification]:
    """
    Creates a notification for a target user and broadcasts it in real-time if they are online.
    """
    # Prevent notifying oneself
    if receiver_id == sender_profile_id:
        return None

    notification_id = secrets.randbits(52)
    db_noti = models.Notification(
        notification_id=notification_id,
        receiver_id=receiver_id,
        user_id=sender_profile_id,
        notification_type=notification_type,
        reference_id=reference_id,
        is_read=False
    )
    db.add(db_noti)
    db.commit()
    db.refresh(db_noti)

    # Broadcast notification via WebSocket if receiver is connected
    try:
        ws = get_ws_manager()
        from crud import crud_sql
        actor_profile = crud_sql.get_profile_by_id(db, sender_profile_id)
        actor_username = actor_profile.username if actor_profile else f"user_{sender_profile_id}"

        # Build descriptive content for real-time toast notifications
        content = "New notification received"
        if notification_type == "follow":
            content = f"@{actor_username} started following you."
        elif notification_type == "follow_accept":
            content = f"@{actor_username} accepted your follow request."
        elif notification_type == "like":
            content = f"@{actor_username} liked your post."
        elif notification_type == "comment":
            content = f"@{actor_username} commented on your post."
        elif notification_type == "message":
            content = f"got 1 message from {actor_username}"

        payload = {
            "notification_id": db_noti.notification_id,
            "receiver_id": db_noti.receiver_id,
            "user_id": db_noti.user_id,
            "notification_type": db_noti.notification_type,
            "reference_id": db_noti.reference_id,
            "is_read": db_noti.is_read,
            "content": content
        }
        ws.broadcast_notification_sync(payload, receiver_id)
    except Exception as err:
        # Prevent websocket errors from breaking DB transaction
        print(f"WS Broadcast error: {err}")

    return db_noti


def get_notifications(db: Session, receiver_id: int, limit: int = 50) -> List[models.Notification]:
    return db.query(models.Notification).filter(
        models.Notification.receiver_id == receiver_id
    ).order_by(models.Notification.notification_id.desc()).limit(limit).all()


def mark_notification_read(db: Session, notification_id: int, receiver_id: int) -> bool:
    db_noti = db.query(models.Notification).filter(
        models.Notification.notification_id == notification_id,
        models.Notification.receiver_id == receiver_id
    ).first()
    if db_noti:
        db_noti.is_read = True
        db.commit()
        db.refresh(db_noti)
        return True
    return False
