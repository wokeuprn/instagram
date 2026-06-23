import os
from datetime import datetime
from typing import Any, Dict, List, Optional
# pyrefly: ignore [missing-import]
from bson import ObjectId
# pyrefly: ignore [missing-import]
from pymongo import MongoClient

# MongoDB Connection Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
mongo_client: MongoClient = MongoClient(MONGO_URI)
mongodb = mongo_client[os.getenv("MONGO_DB", "instagram_mongodb")]

# Collections
likes_col = mongodb["likes"]
auth_logs_col = mongodb["auth_logs"]
audit_logs_col = mongodb["audit_logs"]


# ---------------------------------------------------------------------------
# Likes Operations (unified post, comment, reel, story likes)
# ---------------------------------------------------------------------------

def add_like(profile_id: int, target_id: int, target_type: str) -> str:
    """
    Inserts a like for a given target (post, comment, reel, story).
    Returns the inserted document ID as a string.
    """
    like_doc = {
        "profile_id": profile_id,
        "target_id": target_id,
        "target_type": target_type,  # 'post', 'comment', 'reel', 'story'
        "liked_at": datetime.utcnow()
    }
    # Use update_one with upsert to prevent duplicate likes
    result = likes_col.update_one(
        {"profile_id": profile_id, "target_id": target_id, "target_type": target_type},
        {"$setOnInsert": like_doc},
        upsert=True
    )
    # If a document was upserted, return its ID
    if result.upserted_id:
        return str(result.upserted_id)
    
    # Otherwise return the existing document's ID
    existing = likes_col.find_one(
        {"profile_id": profile_id, "target_id": target_id, "target_type": target_type}
    )
    return str(existing["_id"]) if existing else ""


def remove_like(profile_id: int, target_id: int, target_type: str) -> bool:
    """
    Removes a like for a target. Returns True if a document was deleted.
    """
    result = likes_col.delete_one({
        "profile_id": profile_id,
        "target_id": target_id,
        "target_type": target_type
    })
    return result.deleted_count > 0


def get_likes_for_target(target_id: int, target_type: str) -> List[Dict[str, Any]]:
    """
    Returns a list of likes for a specific target.
    """
    cursor = likes_col.find({"target_id": target_id, "target_type": target_type})
    return list(cursor)


def get_likes_by_profile(profile_id: int) -> List[Dict[str, Any]]:
    """
    Returns all likes made by a specific profile.
    """
    cursor = likes_col.find({"profile_id": profile_id})
    return list(cursor)


# ---------------------------------------------------------------------------
# Auth Logs Operations (login and logout tracking)
# ---------------------------------------------------------------------------

def log_auth_action(
    profile_id: int, 
    action: str, 
    ip_address: Optional[str] = None, 
    user_agent: Optional[str] = None
) -> str:
    """
    Logs an authentication action (e.g., 'login', 'logout').
    """
    log_doc = {
        "profile_id": profile_id,
        "action": action,  # 'login' or 'logout'
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": datetime.utcnow()
    }
    result = auth_logs_col.insert_one(log_doc)
    return str(result.inserted_id)


def get_auth_logs(profile_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves the recent authentication logs for a profile.
    """
    cursor = auth_logs_col.find({"profile_id": profile_id}).sort("timestamp", -1).limit(limit)
    return list(cursor)


# ---------------------------------------------------------------------------
# Auditing Operations (username history, bio history, search history)
# ---------------------------------------------------------------------------

def log_username_change(profile_id: int, old_username: str, new_username: str) -> str:
    """
    Logs a username change event.
    """
    audit_doc = {
        "profile_id": profile_id,
        "audit_type": "username_change",
        "old_value": old_username,
        "new_value": new_username,
        "timestamp": datetime.utcnow()
    }
    result = audit_logs_col.insert_one(audit_doc)
    return str(result.inserted_id)


def log_bio_change(profile_id: int, old_bio: str, new_bio: str) -> str:
    """
    Logs a profile bio change event.
    """
    audit_doc = {
        "profile_id": profile_id,
        "audit_type": "bio_change",
        "old_value": old_bio,
        "new_value": new_bio,
        "timestamp": datetime.utcnow()
    }
    result = audit_logs_col.insert_one(audit_doc)
    return str(result.inserted_id)


def log_search_query(profile_id: int, search_term: str) -> str:
    """
    Logs a search query query for auditing/history.
    """
    audit_doc = {
        "profile_id": profile_id,
        "audit_type": "search_query",
        "old_value": None,
        "new_value": search_term,
        "timestamp": datetime.utcnow()
    }
    result = audit_logs_col.insert_one(audit_doc)
    return str(result.inserted_id)


def get_audit_logs(
    profile_id: int, 
    audit_type: Optional[str] = None, 
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Retrieves the audit logs for a profile, optionally filtered by audit_type.
    """
    query = {"profile_id": profile_id}
    if audit_type:
        query["audit_type"] = audit_type
    cursor = audit_logs_col.find(query).sort("timestamp", -1).limit(limit)
    return list(cursor)


def get_all_audit_logs(
    audit_type: Optional[str] = None,
    profile_id: Optional[int] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Retrieves system-wide audit logs, optionally filtered by type or profile ID.
    """
    query = {}
    if audit_type:
        query["audit_type"] = audit_type
    if profile_id is not None:
        query["profile_id"] = profile_id
    cursor = audit_logs_col.find(query).sort("timestamp", -1).limit(limit)
    return list(cursor)


def get_all_auth_logs(
    profile_id: Optional[int] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Retrieves system-wide auth logs, optionally filtered by profile ID.
    """
    query = {}
    if profile_id is not None:
        query["profile_id"] = profile_id
    cursor = auth_logs_col.find(query).sort("timestamp", -1).limit(limit)
    return list(cursor)

