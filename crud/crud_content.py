from datetime import datetime, timedelta
import secrets
from typing import List, Optional
import re
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


def process_hashtags(db: Session, target_id: int, text: str, target_type: str):
    if not text:
        return
    tags = re.findall(r"#(\w+)", text)
    for tag_name in set(tags):
        tag_name_lower = tag_name.lower()
        # Find or create hashtag
        tag = db.query(models.Hashtag).filter(models.Hashtag.tag_name == tag_name_lower).first()
        if not tag:
            tag = models.Hashtag(hashtag_id=secrets.randbits(52), tag_name=tag_name_lower)
            db.add(tag)
            db.flush()
        
        # Link hashtag to post/reel
        if target_type == "post":
            link = models.PostHashtag(post_id=target_id, hashtag_id=tag.hashtag_id)
            db.add(link)
        elif target_type == "reel":
            link = models.ReelHashtag(reel_id=target_id, hashtag_id=tag.hashtag_id)
            db.add(link)
        
        # Update usage index
        idx = db.query(models.HashtagSearchIndex).filter(models.HashtagSearchIndex.hashtag_id == tag.hashtag_id).first()
        if idx:
            idx.usage_count += 1
        else:
            idx = models.HashtagSearchIndex(hashtag_id=tag.hashtag_id, usage_count=1)
            db.add(idx)
    db.commit()


# ---------------------------------------------------------------------------
# Posts Operations
# ---------------------------------------------------------------------------

def create_post(db: Session, profile_id: int, request: schemas.PostCreateRequest) -> models.Post:
    post_id = generate_random_id()
    db_post = models.Post(
        post_id=post_id,
        profile_id=profile_id,
        caption=request.caption,
        location=request.location,
        visibility=request.visibility,
        media_url=request.media_url,
        created_at=datetime.utcnow()
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)

    # Process hashtags and search indexing
    caption_text = request.caption or ""
    process_hashtags(db, post_id, caption_text, "post")
    from .crud_search import index_post_content
    index_post_content(db, post_id, f"{caption_text} {request.location or ''}".strip())

    return db_post


def get_post_by_id(db: Session, post_id: int) -> Optional[models.Post]:
    return db.query(models.Post).filter(models.Post.post_id == post_id).first()


def delete_post(db: Session, post_id: int, profile_id: int, is_admin: bool = False) -> bool:
    query = db.query(models.Post).filter(models.Post.post_id == post_id)
    if not is_admin:
        query = query.filter(models.Post.profile_id == profile_id)
    db_post = query.first()
    if db_post:
        # Cascade delete comments manually or trust SQLAlchemy cascade
        db.delete(db_post)
        db.commit()
        return True
    return False


def get_profile_posts(db: Session, profile_id: int) -> List[models.Post]:
    return db.query(models.Post).filter(
        models.Post.profile_id == profile_id
    ).order_by(desc(models.Post.created_at)).all()


def get_feed_posts(db: Session, profile_id: int, limit: int = 20) -> List[models.Post]:
    """
    Retrieves posts from profiles that the current user follows + the user's own posts,
    sorted by created_at DESC.
    """
    # Get followed profile IDs
    followed_ids = db.query(models.Follow.following_id).filter(
        models.Follow.follower_id == profile_id
    ).all()
    followed_ids = [r[0] for r in followed_ids]
    
    # Include own posts
    profile_ids_to_query = followed_ids + [profile_id]

    return db.query(models.Post).filter(
        models.Post.profile_id.in_(profile_ids_to_query)
    ).order_by(desc(models.Post.created_at)).limit(limit).all()


# ---------------------------------------------------------------------------
# Comments Operations
# ---------------------------------------------------------------------------

def create_post_comment(
    db: Session, 
    post_id: int, 
    profile_id: int, 
    request: schemas.CommentCreateRequest
) -> models.PostComment:
    comment_id = generate_random_id()
    db_comment = models.PostComment(
        comment_id=comment_id,
        post_id=post_id,
        profile_id=profile_id,
        comment_text=request.comment_text,
        created_at=datetime.utcnow()
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    # Trigger Notification for Post Owner
    try:
        from .crud_notifications import create_notification
        post = get_post_by_id(db, post_id)
        if post:
            create_notification(
                db,
                receiver_id=post.profile_id,
                sender_profile_id=profile_id,
                notification_type="comment",
                reference_id=comment_id
            )
    except Exception as noti_err:
        print(f"Failed to create comment notification: {noti_err}")

    return db_comment


def get_post_comments(db: Session, post_id: int) -> List[models.PostComment]:
    return db.query(models.PostComment).filter(
        models.PostComment.post_id == post_id
    ).order_by(models.PostComment.created_at).all()


def delete_post_comment(db: Session, comment_id: int, profile_id: int, is_admin: bool = False) -> bool:
    db_comment = db.query(models.PostComment).filter(models.PostComment.comment_id == comment_id).first()
    if not db_comment:
        return False
    if is_admin or db_comment.profile_id == profile_id or db_comment.post.profile_id == profile_id:
        db.delete(db_comment)
        db.commit()
        return True
    return False


# ---------------------------------------------------------------------------
# Reels Operations
# ---------------------------------------------------------------------------

def create_reel(db: Session, profile_id: int, request: schemas.ReelCreateRequest) -> models.Reel:
    reel_id = generate_random_id()
    db_reel = models.Reel(
        reel_id=reel_id,
        profile_id=profile_id,
        caption=request.caption,
        duration=request.duration,
        media_url=request.media_url,
        created_at=datetime.utcnow()
    )
    db.add(db_reel)
    db.commit()
    db.refresh(db_reel)

    # Process hashtags and search indexing
    caption_text = request.caption or ""
    process_hashtags(db, reel_id, caption_text, "reel")
    from .crud_search import index_reel_content
    index_reel_content(db, reel_id, caption_text)

    return db_reel


def get_reel_by_id(db: Session, reel_id: int) -> Optional[models.Reel]:
    return db.query(models.Reel).filter(models.Reel.reel_id == reel_id).first()


def delete_reel(db: Session, reel_id: int, profile_id: int, is_admin: bool = False) -> bool:
    query = db.query(models.Reel).filter(models.Reel.reel_id == reel_id)
    if not is_admin:
        query = query.filter(models.Reel.profile_id == profile_id)
    db_reel = query.first()
    if db_reel:
        db.delete(db_reel)
        db.commit()
        return True
    return False


# ---------------------------------------------------------------------------
# Stories Operations (Expires after 24 hours)
# ---------------------------------------------------------------------------

def create_story(db: Session, profile_id: int, request: schemas.StoryCreateRequest) -> models.Story:
    story_id = generate_random_id()
    created_time = datetime.utcnow()
    expires_time = created_time + timedelta(hours=24)
    db_story = models.Story(
        story_id=story_id,
        profile_id=profile_id,
        media_url=request.media_url,
        created_at=created_time,
        expires_at=expires_time
    )
    db.add(db_story)
    db.commit()
    db.refresh(db_story)
    return db_story


def get_active_stories_for_following(db: Session, profile_id: int) -> List[models.Story]:
    """
    Returns stories that have not expired from followed users + own stories.
    """
    followed_ids = db.query(models.Follow.following_id).filter(
        models.Follow.follower_id == profile_id
    ).all()
    followed_ids = [r[0] for r in followed_ids]
    profile_ids_to_query = followed_ids + [profile_id]

    now = datetime.utcnow()
    return db.query(models.Story).filter(
        models.Story.profile_id.in_(profile_ids_to_query),
        models.Story.expires_at > now
    ).order_by(desc(models.Story.created_at)).all()


def create_story_view(db: Session, story_id: int, viewer_id: int) -> models.StoryView:
    # Check if view already exists
    existing = db.query(models.StoryView).filter(
        models.StoryView.story_id == story_id,
        models.StoryView.viewer_id == viewer_id
    ).first()
    if existing:
        return existing

    db_view = models.StoryView(
        story_id=story_id,
        viewer_id=viewer_id,
        viewed_at=datetime.utcnow()
    )
    db.add(db_view)
    db.commit()
    db.refresh(db_view)
    return db_view


def get_reels_feed(db: Session, limit: int = 50) -> List[models.Reel]:
    return db.query(models.Reel).order_by(desc(models.Reel.created_at)).limit(limit).all()


def create_reel_comment(db: Session, reel_id: int, profile_id: int, comment_text: str) -> models.ReelComment:
    comment_id = generate_random_id()
    db_comment = models.ReelComment(
        reel_comment_id=comment_id,
        reel_id=reel_id,
        profile_id=profile_id,
        comment_text=comment_text
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


def get_reel_comments(db: Session, reel_id: int) -> List[models.ReelComment]:
    return db.query(models.ReelComment).filter(models.ReelComment.reel_id == reel_id).all()


def get_profile_reels(db: Session, profile_id: int) -> List[models.Reel]:
    return db.query(models.Reel).filter(models.Reel.profile_id == profile_id).order_by(desc(models.Reel.created_at)).all()


