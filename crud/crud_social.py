from datetime import datetime
from typing import List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import or_, and_

from database import models


def follow_profile(db: Session, follower_id: int, following_id: int) -> models.Follow:
    """
    Directly creates a follow relationship between two profiles.
    """
    # Check if already following
    existing = db.query(models.Follow).filter(
        models.Follow.follower_id == follower_id,
        models.Follow.following_id == following_id
    ).first()
    if existing:
        return existing

    db_follow = models.Follow(
        follower_id=follower_id,
        following_id=following_id,
        followed_at=datetime.utcnow()
    )
    db.add(db_follow)
    db.commit()
    db.refresh(db_follow)

    # Trigger follow notification
    try:
        from .crud_notifications import create_notification
        create_notification(
            db,
            receiver_id=following_id,
            sender_profile_id=follower_id,
            notification_type="follow",
            reference_id=follower_id
        )
    except Exception as e:
        print(f"Failed to create follow notification: {e}")

    return db_follow


def unfollow_profile(db: Session, follower_id: int, following_id: int) -> bool:
    """
    Removes a follow relationship. Returns True if deleted.
    """
    db_follow = db.query(models.Follow).filter(
        models.Follow.follower_id == follower_id,
        models.Follow.following_id == following_id
    ).first()
    if db_follow:
        db.delete(db_follow)
        db.commit()
        return True
    return False


def create_follow_request(db: Session, sender_id: int, receiver_id: int) -> models.FollowRequest:
    """
    Creates a pending follow request from sender to receiver.
    """
    # Check if a request already exists
    existing = db.query(models.FollowRequest).filter(
        models.FollowRequest.sender_id == sender_id,
        models.FollowRequest.receiver_id == receiver_id
    ).first()
    if existing:
        return existing

    # Generate random request_id for primary key
    import secrets
    req_id = secrets.randbits(63)
    db_req = models.FollowRequest(
        request_id=req_id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(db_req)
    db.commit()
    db.refresh(db_req)

    # Trigger follow request notification
    try:
        from .crud_notifications import create_notification
        create_notification(
            db,
            receiver_id=receiver_id,
            sender_profile_id=sender_id,
            notification_type="follow_request",
            reference_id=req_id
        )
    except Exception as e:
        print(f"Failed to create follow request notification: {e}")

    return db_req


def get_pending_requests(db: Session, receiver_id: int) -> List[models.FollowRequest]:
    """
    Lists all pending follow requests received by a profile.
    """
    return db.query(models.FollowRequest).filter(
        models.FollowRequest.receiver_id == receiver_id,
        models.FollowRequest.status == "pending"
    ).all()


def respond_to_follow_request(
    db: Session, 
    request_id: int, 
    receiver_id: int, 
    accept: bool
) -> Optional[models.FollowRequest]:
    """
    Accepts or rejects a follow request.
    If accepted, establishes the follow relationship.
    """
    db_req = db.query(models.FollowRequest).filter(
        models.FollowRequest.request_id == request_id,
        models.FollowRequest.receiver_id == receiver_id,
        models.FollowRequest.status == "pending"
    ).first()

    if not db_req:
        return None

    if accept:
        db_req.status = "accepted"
        # Create follow entry
        follow_profile(db, db_req.sender_id, db_req.receiver_id)
    else:
        db_req.status = "rejected"

    db.commit()
    db.refresh(db_req)
    return db_req


def block_profile(db: Session, blocker_id: int, blocked_id: int) -> models.Block:
    """
    Blocks a profile, blocking interactions, and automatically unfollows both ways.
    """
    # Check if already blocked
    existing = db.query(models.Block).filter(
        models.Block.blocker_id == blocker_id,
        models.Block.blocked_id == blocked_id
    ).first()
    if existing:
        return existing

    # Remove any existing follows (both ways)
    unfollow_profile(db, blocker_id, blocked_id)
    unfollow_profile(db, blocked_id, blocker_id)

    db_block = models.Block(
        blocker_id=blocker_id,
        blocked_id=blocked_id,
        blocked_at=datetime.utcnow()
    )
    db.add(db_block)
    db.commit()
    db.refresh(db_block)
    return db_block


def unblock_profile(db: Session, blocker_id: int, blocked_id: int) -> bool:
    """
    Unblocks a profile.
    """
    db_block = db.query(models.Block).filter(
        models.Block.blocker_id == blocker_id,
        models.Block.blocked_id == blocked_id
    ).first()
    if db_block:
        db.delete(db_block)
        db.commit()
        return True
    return False


def is_blocked(db: Session, profile_a_id: int, profile_b_id: int) -> bool:
    """
    Checks if a block exists between profile_a and profile_b (either way).
    """
    block = db.query(models.Block).filter(
        or_(
            and_(models.Block.blocker_id == profile_a_id, models.Block.blocked_id == profile_b_id),
            and_(models.Block.blocker_id == profile_b_id, models.Block.blocked_id == profile_a_id)
        )
    ).first()
    return block is not None


def get_followers(db: Session, profile_id: int) -> List[models.Profile]:
    """
    Returns the profiles that follow this user.
    """
    return db.query(models.Profile).join(
        models.Follow,
        models.Follow.follower_id == models.Profile.profile_id
    ).filter(
        models.Follow.following_id == profile_id
    ).all()


def get_following(db: Session, profile_id: int) -> List[models.Profile]:
    """
    Returns the profiles that this user follows.
    """
    return db.query(models.Profile).join(
        models.Follow,
        models.Follow.following_id == models.Profile.profile_id
    ).filter(
        models.Follow.follower_id == profile_id
    ).all()
