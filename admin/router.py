# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Query, status
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from database import get_db, models, mongodb
from crud import crud_sql, crud_content
from dependencies import get_current_admin
import schemas

admin_router = APIRouter()


@admin_router.get("/stats", response_model=schemas.AdminStatsResponse)
def get_admin_stats(
    admin: models.Profile = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieves global statistics across the platform.
    """
    total_users = db.query(models.User).count()
    total_profiles = db.query(models.Profile).count()
    total_posts = db.query(models.Post).count()
    total_reels = db.query(models.Reel).count()
    total_comments = db.query(models.PostComment).count()

    return schemas.AdminStatsResponse(
        total_users=total_users,
        total_profiles=total_profiles,
        total_posts=total_posts,
        total_reels=total_reels,
        total_comments=total_comments
    )


@admin_router.get("/audit-logs")
def get_admin_audit_logs(
    audit_type: Optional[str] = Query(None, description="Filter logs by action type"),
    profile_id: Optional[int] = Query(None, description="Filter logs by profile ID"),
    limit: int = Query(50, ge=1, le=100),
    admin: models.Profile = Depends(get_current_admin)
):
    """
    Retrieves system-wide audit logs from MongoDB.
    """
    try:
        logs = mongodb.get_all_audit_logs(audit_type=audit_type, profile_id=profile_id, limit=limit)
        formatted = []
        for log in logs:
            formatted.append({
                "log_id": str(log["_id"]),
                "profile_id": str(log["profile_id"]),
                "audit_type": log["audit_type"],
                "old_value": log["old_value"],
                "new_value": log["new_value"],
                "timestamp": log["timestamp"].isoformat()
            })
        return formatted
    except Exception as mongo_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {mongo_err}"
        )


@admin_router.get("/auth-logs")
def get_admin_auth_logs(
    profile_id: Optional[int] = Query(None, description="Filter by profile ID"),
    limit: int = Query(50, ge=1, le=100),
    admin: models.Profile = Depends(get_current_admin)
):
    """
    Retrieves system-wide auth logs from MongoDB.
    """
    try:
        logs = mongodb.get_all_auth_logs(profile_id=profile_id, limit=limit)
        formatted = []
        for log in logs:
            formatted.append({
                "log_id": str(log["_id"]),
                "profile_id": str(log["profile_id"]),
                "action": log["action"],
                "ip_address": log.get("ip_address"),
                "user_agent": log.get("user_agent"),
                "timestamp": log["timestamp"].isoformat()
            })
        return formatted
    except Exception as mongo_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {mongo_err}"
        )


@admin_router.put("/users/{user_id}/status")
def admin_update_user_status(
    user_id: int,
    request: schemas.UserStatusUpdateRequest,
    admin: models.Profile = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Suspends or reactivates a user's account.
    """
    status_val = request.status.lower()
    if status_val not in ["active", "suspended"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status value. Must be 'active' or 'suspended'."
        )
    
    updated_user = crud_sql.update_user_status(db, user_id, status_val)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {"message": f"User status successfully updated to {status_val}", "user_id": str(user_id), "status": status_val}


@admin_router.put("/profiles/{profile_id}/verify")
def admin_verify_profile(
    profile_id: int,
    request: schemas.ProfileVerificationRequest,
    admin: models.Profile = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Toggles verified status for a user's profile.
    """
    updated_profile = crud_sql.update_profile_verification(db, profile_id, request.verified_status)
    if not updated_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    action_str = "verified" if request.verified_status else "unverified"
    return {"message": f"Profile successfully {action_str}", "profile_id": str(profile_id), "verified_status": request.verified_status}


@admin_router.delete("/posts/{post_id}")
def admin_delete_post(
    post_id: int,
    admin: models.Profile = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Deletes any post globally as an admin.
    """
    deleted = crud_content.delete_post(db, post_id, profile_id=admin.profile_id, is_admin=True)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"message": "Post successfully moderated/deleted by admin"}


@admin_router.delete("/reels/{reel_id}")
def admin_delete_reel(
    reel_id: int,
    admin: models.Profile = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Deletes any reel globally as an admin.
    """
    deleted = crud_content.delete_reel(db, reel_id, profile_id=admin.profile_id, is_admin=True)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reel not found")
    return {"message": "Reel successfully moderated/deleted by admin"}


@admin_router.delete("/comments/{comment_id}")
def admin_delete_comment(
    comment_id: int,
    admin: models.Profile = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Deletes any comment globally as an admin.
    """
    deleted = crud_content.delete_post_comment(db, comment_id, profile_id=admin.profile_id, is_admin=True)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"message": "Comment successfully moderated/deleted by admin"}


@admin_router.post("/register", response_model=schemas.ProfileResponse, status_code=status.HTTP_201_CREATED)
def admin_register_new_admin(
    request: schemas.UserRegisterRequest,
    admin: models.Profile = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Registers a new user and profile with account_type='admin'.
    Only an existing admin can perform this operation.
    """
    existing_user = db.query(models.User).filter(
        (models.User.email == request.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )
        
    existing_profile = db.query(models.Profile).filter(
        (models.Profile.username == request.username)
    ).first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A profile with this username already exists."
        )

    # Create User
    db_user = models.User(
        full_name=request.full_name,
        email=request.email,
        phone=request.phone,
        status="active",
        is_email_verified=True,
        is_phone_verified=True,
        created_at=datetime.utcnow()
    )
    db.add(db_user)
    db.flush()

    import auth
    hashed_password = auth.hash_password(request.password)

    # Create Profile with account_type="admin"
    db_profile = models.Profile(
        user_id=db_user.user_id,
        username=request.username,
        password=hashed_password,
        full_name=request.full_name,
        account_type="admin",
        is_private=False,
        verified_status=True,
        failed_login_attempts=0
    )
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)

    # Index Profile for search
    try:
        from crud.crud_search import index_user_profile
        index_user_profile(db, db_profile.profile_id)
    except Exception as search_err:
        print(f"Search indexing error: {search_err}")

    return db_profile

