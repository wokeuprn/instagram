from typing import List, Dict, Any
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import or_
from database import models


def index_user_profile(db: Session, profile_id: int):
    """
    Updates or inserts search index for a user profile.
    """
    profile = db.query(models.Profile).filter(models.Profile.profile_id == profile_id).first()
    if not profile:
        return

    # Combine searchable attributes
    searchable_text = f"{profile.username} {profile.full_name or ''} {profile.bio or ''}".strip().lower()

    index_entry = db.query(models.UserSearchIndex).filter(models.UserSearchIndex.profile_id == profile_id).first()
    if index_entry:
        index_entry.searchable_text = searchable_text
    else:
        index_entry = models.UserSearchIndex(profile_id=profile_id, searchable_text=searchable_text)
        db.add(index_entry)
    db.commit()


def index_post_content(db: Session, post_id: int, text: str):
    """
    Updates or inserts search index for a post.
    """
    index_entry = db.query(models.PostSearchIndex).filter(models.PostSearchIndex.post_id == post_id).first()
    if index_entry:
        index_entry.searchable_text = text.lower()
    else:
        index_entry = models.PostSearchIndex(post_id=post_id, searchable_text=text.lower())
        db.add(index_entry)
    db.commit()


def index_reel_content(db: Session, reel_id: int, text: str):
    """
    Updates or inserts search index for a reel.
    """
    index_entry = db.query(models.ReelSearchIndex).filter(models.ReelSearchIndex.reel_id == reel_id).first()
    if index_entry:
        index_entry.searchable_text = text.lower()
    else:
        index_entry = models.ReelSearchIndex(reel_id=reel_id, searchable_text=text.lower())
        db.add(index_entry)
    db.commit()


def global_search(db: Session, query: str) -> Dict[str, List[Any]]:
    """
    Performs a global search across profiles, posts, reels, and hashtags.
    """
    q = query.lower().strip()
    if not q:
        return {"profiles": [], "posts": [], "reels": [], "hashtags": []}

    # 1. Search User Profiles
    profile_ids = db.query(models.UserSearchIndex.profile_id).filter(
        models.UserSearchIndex.searchable_text.like(f"%{q}%")
    ).all()
    profile_ids = [r[0] for r in profile_ids]
    profiles = db.query(models.Profile).filter(models.Profile.profile_id.in_(profile_ids)).all() if profile_ids else []

    # 2. Search Posts
    post_ids = db.query(models.PostSearchIndex.post_id).filter(
        models.PostSearchIndex.searchable_text.like(f"%{q}%")
    ).all()
    post_ids = [r[0] for r in post_ids]
    posts = db.query(models.Post).filter(models.Post.post_id.in_(post_ids)).all() if post_ids else []

    # 3. Search Reels
    reel_ids = db.query(models.ReelSearchIndex.reel_id).filter(
        models.ReelSearchIndex.searchable_text.like(f"%{q}%")
    ).all()
    reel_ids = [r[0] for r in reel_ids]
    reels = db.query(models.Reel).filter(models.Reel.reel_id.in_(reel_ids)).all() if reel_ids else []

    # 4. Search Hashtags
    hashtags = db.query(models.Hashtag).filter(
        models.Hashtag.tag_name.like(f"%{q}%")
    ).all()
    
    formatted_hashtags = []
    for tag in hashtags:
        idx = db.query(models.HashtagSearchIndex).filter(models.HashtagSearchIndex.hashtag_id == tag.hashtag_id).first()
        formatted_hashtags.append({
            "hashtag_id": tag.hashtag_id,
            "tag_name": tag.tag_name,
            "usage_count": idx.usage_count if idx else 0
        })

    return {
        "profiles": profiles,
        "posts": posts,
        "reels": reels,
        "hashtags": formatted_hashtags
    }
