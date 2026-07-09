import os
import sys
from datetime import datetime
import secrets
from typing import List, Optional

# Add project root to sys.path to allow direct execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pyrefly: ignore[missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore[missing-import]
from sqlalchemy import desc

# pyrefly: ignore[missing-import]
from database import models
# pyrefly: ignore[missing-import]
import schemas


def generate_random_id() -> int:
    return secrets.randbits(52)


# ---------------------------------------------------------------------------
# Conversations Operations
# ---------------------------------------------------------------------------

def get_or_create_direct_conversation(
    db: Session, 
    sender_id: int, 
    receiver_id: int
) -> models.Conversation:
    """
    Finds a direct 1-to-1 conversation between two profiles.
    Creates a new one if it doesn't exist.
    """
    # Query for a common "direct" conversation ID that both profiles are members of
    subq1 = db.query(models.ConversationMember.conversation_id).filter(
        models.ConversationMember.profile_id == sender_id
    ).subquery()
    
    subq2 = db.query(models.ConversationMember.conversation_id).filter(
        models.ConversationMember.profile_id == receiver_id
    ).subquery()
    
    common_conv_id = db.query(models.Conversation.conversation_id).join(
        subq1, models.Conversation.conversation_id == subq1.c.conversation_id
    ).join(
        subq2, models.Conversation.conversation_id == subq2.c.conversation_id
    ).filter(
        models.Conversation.conversation_type == "direct"
    ).scalar()

    if common_conv_id:
        return db.query(models.Conversation).filter(
            models.Conversation.conversation_id == common_conv_id
        ).first()

    # Create new direct conversation
    conv_id = generate_random_id()
    now = datetime.utcnow()
    db_conv = models.Conversation(
        conversation_id=conv_id,
        conversation_type="direct",
        created_at=now,
        last_message_at=now
    )
    db.add(db_conv)

    # Add members
    member_a = models.ConversationMember(
        conversation_id=conv_id,
        profile_id=sender_id,
        joined_at=now
    )
    member_b = models.ConversationMember(
        conversation_id=conv_id,
        profile_id=receiver_id,
        joined_at=now
    )
    db.add(member_a)
    db.add(member_b)
    db.commit()
    db.refresh(db_conv)
    return db_conv


def create_group_conversation(
    db: Session,
    sender_id: int,
    request: schemas.GroupConversationCreateRequest
) -> models.Conversation:
    """
    Creates a new group conversation with the specified members.
    """
    from crud import crud_sql
    
    conv_id = generate_random_id()
    now = datetime.utcnow()
    db_conv = models.Conversation(
        conversation_id=conv_id,
        conversation_type="group",
        name=request.name,
        created_at=now,
        last_message_at=now
    )
    db.add(db_conv)

    sender_member = models.ConversationMember(
        conversation_id=conv_id,
        profile_id=sender_id,
        joined_at=now
    )
    db.add(sender_member)

    for username in request.member_usernames:
        recipient = crud_sql.get_profile_by_username(db, username)
        if recipient and recipient.profile_id != sender_id:
            member = models.ConversationMember(
                conversation_id=conv_id,
                profile_id=recipient.profile_id,
                joined_at=now
            )
            db.add(member)

    db.commit()
    db.refresh(db_conv)

    # Notify added members about the new group conversation in real-time
    try:
        from dependencies import ws_manager
        for member in db_conv.members:
            if member.profile_id != sender_id:
                payload = {
                    "type": "new_conversation",
                    "data": {
                        "conversation_id": str(db_conv.conversation_id),
                        "conversation_type": db_conv.conversation_type,
                        "name": db_conv.name,
                        "created_at": db_conv.created_at.isoformat(),
                        "last_message": "Click to open chat history"
                    }
                }
                ws_manager.send_personal_message_sync(payload, member.profile_id)
    except Exception as err:
        print(f"Failed to push new group conversation WS event: {err}")

    return db_conv


def get_profile_conversations(db: Session, profile_id: int) -> List[models.Conversation]:
    """
    Lists all conversations a profile belongs to, ordered by latest message activity.
    """
    return db.query(models.Conversation).join(
        models.ConversationMember,
        models.ConversationMember.conversation_id == models.Conversation.conversation_id
    ).filter(
        models.ConversationMember.profile_id == profile_id
    ).order_by(desc(models.Conversation.last_message_at)).all()


# ---------------------------------------------------------------------------
# Messages Operations
# ---------------------------------------------------------------------------

def send_message(
    db: Session, 
    conversation_id: int, 
    sender_id: int, 
    request: schemas.MessageCreateRequest
) -> models.Message:
    """
    Sends a message in a conversation.
    """
    msg_id = generate_random_id()
    db_message = models.Message(
        message_id=msg_id,
        conversation_id=conversation_id,
        sender_id=sender_id,
        message_type=request.message_type,
        content=request.content,
        sent_at=datetime.utcnow()
    )
    db.add(db_message)
    
    # Update last_message_at on the conversation
    db.query(models.Conversation).filter(
        models.Conversation.conversation_id == conversation_id
    ).update({models.Conversation.last_message_at: db_message.sent_at})

    db.commit()
    db.refresh(db_message)

    # Notify conversation members and push real-time message via WebSockets
    try:
        import asyncio
        from dependencies import ws_manager
        from .crud_notifications import create_notification
        
        # Get members of conversation
        members = db.query(models.ConversationMember).filter(
            models.ConversationMember.conversation_id == conversation_id
        ).all()

        sender_profile = db.query(models.Profile).filter(models.Profile.profile_id == sender_id).first()
        sender_username = sender_profile.username if sender_profile else "unknown"
        sender_avatar = sender_profile.profile_picture if sender_profile else None

        for member in members:
            if member.profile_id != sender_id:
                # 1. Trigger notification
                create_notification(
                    db,
                    receiver_id=member.profile_id,
                    sender_profile_id=sender_id,
                    notification_type="message",
                    reference_id=db_message.message_id
                )
                
                # 2. Push message via WebSocket
                msg_payload = {
                    "type": "message",
                    "data": {
                        "message_id": str(db_message.message_id),
                        "conversation_id": str(db_message.conversation_id),
                        "sender_id": str(db_message.sender_id),
                        "message_type": db_message.message_type,
                        "content": db_message.content,
                        "sent_at": db_message.sent_at.isoformat(),
                        "sender_username": sender_username,
                        "sender_avatar": sender_avatar
                    }
                }
                ws_manager.send_personal_message_sync(msg_payload, member.profile_id)
    except Exception as err:
        print(f"Failed to deliver real-time messages/notifications: {err}")

    return db_message


def get_conversation_messages(
    db: Session, 
    conversation_id: int, 
    limit: int = 50
) -> List[models.Message]:
    """
    Retrieves message history for a conversation.
    """
    return db.query(models.Message).filter(
        models.Message.conversation_id == conversation_id
    ).order_by(models.Message.sent_at).limit(limit).all()


# ---------------------------------------------------------------------------
# Message Status (Seen) & Reactions
# ---------------------------------------------------------------------------

def mark_messages_as_seen(
    db: Session, 
    conversation_id: int, 
    message_ids: List[int], 
    profile_id: int
) -> None:
    """
    Marks messages in a conversation as read/seen.
    """
    now = datetime.utcnow()
    for msg_id in message_ids:
        # Check if already seen
        existing = db.query(models.MessageSeen).filter(
            models.MessageSeen.message_id == msg_id,
            models.MessageSeen.profile_id == profile_id
        ).first()
        if not existing:
            db_seen = models.MessageSeen(
                message_id=msg_id,
                profile_id=profile_id,
                seen_at=now
            )
            db.add(db_seen)
    db.commit()


def add_message_reaction(
    db: Session, 
    message_id: int, 
    profile_id: int, 
    emoji: str
) -> models.MessageReaction:
    """
    Adds or updates an emoji reaction on a message.
    """
    existing = db.query(models.MessageReaction).filter(
        models.MessageReaction.message_id == message_id,
        models.MessageReaction.profile_id == profile_id
    ).first()

    if existing:
        existing.emoji = emoji
        db.commit()
        db.refresh(existing)
        return existing

    react_id = generate_random_id()
    db_reaction = models.MessageReaction(
        reaction_id=react_id,
        message_id=message_id,
        profile_id=profile_id,
        emoji=emoji
    )
    db.add(db_reaction)
    db.commit()
    db.refresh(db_reaction)
    return db_reaction


def add_members_to_group(
    db: Session,
    conversation_id: int,
    usernames: List[str],
    current_profile_id: int
) -> models.Conversation:
    """
    Adds new members to an existing group conversation and notifies them via WebSocket.
    """
    # 1. Fetch conversation
    conv = db.query(models.Conversation).filter(
        models.Conversation.conversation_id == conversation_id
    ).first()
    if not conv:
        raise ValueError("Conversation not found")
    if conv.conversation_type != "group":
        raise ValueError("Cannot add members to a non-group conversation")

    # 2. Check if current user is a member
    is_member = db.query(models.ConversationMember).filter(
        models.ConversationMember.conversation_id == conversation_id,
        models.ConversationMember.profile_id == current_profile_id
    ).first()
    if not is_member:
        raise ValueError("You are not a member of this conversation")

    # 3. Add new members
    from crud import crud_sql
    now = datetime.utcnow()
    existing_member_ids = {m.profile_id for m in conv.members}

    for username in usernames:
        profile = crud_sql.get_profile_by_username(db, username)
        if profile and profile.profile_id not in existing_member_ids:
            new_member = models.ConversationMember(
                conversation_id=conversation_id,
                profile_id=profile.profile_id,
                joined_at=now
            )
            db.add(new_member)
            existing_member_ids.add(profile.profile_id)

    db.commit()
    db.refresh(conv)

    # WebSocket notification to newly added members
    try:
        from dependencies import ws_manager
        for username in usernames:
            profile = crud_sql.get_profile_by_username(db, username)
            if profile and profile.profile_id != current_profile_id:
                payload = {
                    "type": "new_conversation",
                    "data": {
                        "conversation_id": str(conv.conversation_id),
                        "conversation_type": conv.conversation_type,
                        "name": conv.name,
                        "created_at": conv.created_at.isoformat(),
                        "last_message": "You were added to this group"
                    }
                }
                ws_manager.send_personal_message_sync(payload, profile.profile_id)
    except Exception as err:
        print(f"Failed to push new member WS event: {err}")

    return conv


def delete_conversation(db: Session, conversation_id: int, current_profile_id: int) -> bool:
    """
    Deletes a conversation entirely. Cleans up all messages, reactions, seen entries,
    members, and the conversation record itself.
    """
    conv = db.query(models.Conversation).filter(models.Conversation.conversation_id == conversation_id).first()
    if not conv:
        raise ValueError("Conversation not found")

    # Verify membership
    is_member = db.query(models.ConversationMember).filter(
        models.ConversationMember.conversation_id == conversation_id,
        models.ConversationMember.profile_id == current_profile_id
    ).first()
    if not is_member:
        raise ValueError("You are not authorized to delete this conversation")

    # Gather member profiles before deleting relationships
    member_profile_ids = [m.profile_id for m in conv.members]

    # 1. Fetch message IDs in this conversation
    messages = db.query(models.Message).filter(models.Message.conversation_id == conversation_id).all()
    message_ids = [m.message_id for m in messages]

    if message_ids:
        # 2. Delete message reactions
        db.query(models.MessageReaction).filter(models.MessageReaction.message_id.in_(message_ids)).delete(synchronize_session=False)
        # 3. Delete message seen entries
        db.query(models.MessageSeen).filter(models.MessageSeen.message_id.in_(message_ids)).delete(synchronize_session=False)
        # 4. Delete messages
        db.query(models.Message).filter(models.Message.conversation_id == conversation_id).delete(synchronize_session=False)

    # 5. Delete conversation members
    db.query(models.ConversationMember).filter(models.ConversationMember.conversation_id == conversation_id).delete(synchronize_session=False)

    # 6. Delete conversation
    db.query(models.Conversation).filter(models.Conversation.conversation_id == conversation_id).delete(synchronize_session=False)

    db.commit()

    # WebSocket notification
    try:
        from dependencies import ws_manager
        payload = {
            "type": "delete_conversation",
            "data": {
                "conversation_id": str(conversation_id)
            }
        }
        for pid in member_profile_ids:
            ws_manager.send_personal_message_sync(payload, pid)
    except Exception as err:
        print(f"Failed to push delete conversation WS event: {err}")

    return True

