# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Depends, HTTPException, status, Query, File, UploadFile, WebSocket, WebSocketDisconnect
# pyrefly: ignore [missing-import]
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
import os
import uuid
import shutil

from database import get_db, create_tables, models, mongodb
from crud import crud_sql, crud_social, crud_content, crud_messaging
import schemas
from dependencies import get_current_profile, get_current_admin, security
from admin import admin_router

# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse

# Initialize FastAPI application
app = FastAPI(
    title="Instagram Clone Backend REST API",
    description="Unified API combining PostgreSQL (Core Data & Sessions) and MongoDB (Likes, Audits, & Session Logs).",
    version="1.0.0"
)

# Serve static frontend
@app.get("/", response_class=FileResponse)
def serve_index():
    # If static/index.html doesn't exist, we will create it shortly
    return FileResponse("static/index.html")

@app.get("/admin", response_class=FileResponse)
def serve_admin():
    return FileResponse("static/admin.html")

app.mount("/static", StaticFiles(directory="static"), name="static")

# Create tables on startup (PostgreSQL)
@app.on_event("startup")
def on_startup():
    create_tables()

# Register admin router
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])


# Authentication Routes

@app.post("/api/register", response_model=schemas.ProfileResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: schemas.UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Registers a new user and profile in PostgreSQL and logs username creation in MongoDB.
    """
    # Check if email is already registered
    if crud_sql.get_user_by_email(db, request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )
    
    # Check if username is already taken
    if crud_sql.get_profile_by_username(db, request.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already taken"
        )

    # Perform transaction
    profile = crud_sql.create_user_and_profile(db, request)

    # Log initial username assignment in MongoDB
    try:
        mongodb.log_username_change(profile.profile_id, "", request.username)
    except Exception as mongo_err:
        # Gracefully log warning and continue so Postgres registrations don't fail due to Mongo issues
        print(f"MongoDB Logging Warning: {mongo_err}")

    return profile


@app.post("/api/login", response_model=schemas.TokenResponse)
def login_user(request: schemas.UserLoginRequest, db: Session = Depends(get_db)):
    """
    Logs in a user, increments failed attempts, manages lockout, and registers session tokens.
    """
    try:
        profile = crud_sql.handle_login_attempt(db, request)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(val_err)
        )

    # Generate session tokens
    tokens = crud_sql.create_session_tokens(db, profile.profile_id)

    # Log authentication login action to MongoDB
    try:
        mongodb.log_auth_action(
            profile_id=profile.profile_id,
            action="login"
        )
    except Exception as mongo_err:
        print(f"MongoDB Logging Warning: {mongo_err}")

    return tokens


@app.post("/api/logout", status_code=status.HTTP_200_OK)
def logout_user(profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Logs out the current user by revoking all their active sessions.
    """
    # Revoke tokens in PostgreSQL
    crud_sql.revoke_session_tokens(db, profile.profile_id)

    # Log authentication logout action to MongoDB
    try:
        mongodb.log_auth_action(
            profile_id=profile.profile_id,
            action="logout"
        )
    except Exception as mongo_err:
        print(f"MongoDB Logging Warning: {mongo_err}")

    return {"message": "Logged out successfully"}


# Profile Management Routes

@app.get("/api/profile", response_model=schemas.ProfileResponse)
def get_my_profile(profile: models.Profile = Depends(get_current_profile)):
    """
    Retrieves the current authenticated user's profile.
    """
    return profile


@app.put("/api/profile", response_model=schemas.ProfileResponse)
def edit_profile(
    request: schemas.ProfileEditRequest,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Edits profile and user details. Audits bio and username changes in MongoDB.
    """
    # If editing username, make sure it's unique
    if request.username and request.username != profile.username:
        if crud_sql.get_profile_by_username(db, request.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username is already taken"
            )

    old_username = profile.username
    old_bio = profile.bio

    # Save updates
    updated_profile = crud_sql.update_profile(db, profile.profile_id, request)

    # Audit changes in MongoDB
    try:
        if request.username and request.username != old_username:
            mongodb.log_username_change(profile.profile_id, old_username, request.username)
        if request.bio is not None and request.bio != old_bio:
            mongodb.log_bio_change(profile.profile_id, old_bio or "", request.bio)
    except Exception as mongo_err:
        print(f"MongoDB Logging Warning: {mongo_err}")

    return updated_profile


@app.post("/api/verify")
def verify_contact(
    email: Optional[bool] = Query(None, description="Verify user email"),
    phone: Optional[bool] = Query(None, description="Verify user phone"),
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Manually verifies user email or phone numbers.
    """
    response_msg = []
    if email:
        crud_sql.verify_user_email(db, profile.user_id)
        response_msg.append("Email verified successfully")
    if phone:
        crud_sql.verify_user_phone(db, profile.user_id)
        response_msg.append("Phone verified successfully")
        
    if not response_msg:
        return {"message": "No verification actions performed. Please specify email=true or phone=true query parameter."}
        
    return {"message": " & ".join(response_msg)}

# Likes Routes (MongoDB backed)
# ---------------------------------------------------------------------------

@app.post("/api/likes", status_code=status.HTTP_201_CREATED)
def like_content(
    request: schemas.LikeRequest,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Likes a post, comment, reel, or story (stored in MongoDB) and triggers an SQL notification.
    """
    target_type = request.target_type.lower()
    if target_type not in ["post", "comment", "reel", "story"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target_type. Must be 'post', 'comment', 'reel', or 'story'."
        )

    try:
        like_id = mongodb.add_like(
            profile_id=profile.profile_id,
            target_id=request.target_id,
            target_type=target_type
        )
        
        # Trigger Notification for Content Owner
        try:
            from crud.crud_notifications import create_notification
            receiver_id = None
            if target_type == "post":
                target = db.query(models.Post).filter(models.Post.post_id == request.target_id).first()
                if target:
                    receiver_id = target.profile_id
            elif target_type == "comment":
                target = db.query(models.PostComment).filter(models.PostComment.comment_id == request.target_id).first()
                if target:
                    receiver_id = target.profile_id
            elif target_type == "reel":
                target = db.query(models.Reel).filter(models.Reel.reel_id == request.target_id).first()
                if target:
                    receiver_id = target.profile_id
            elif target_type == "story":
                target = db.query(models.Story).filter(models.Story.story_id == request.target_id).first()
                if target:
                    receiver_id = target.profile_id
            
            if receiver_id:
                create_notification(
                    db,
                    receiver_id=receiver_id,
                    sender_profile_id=profile.profile_id,
                    notification_type="like",
                    reference_id=request.target_id
                )
        except Exception as noti_err:
            print(f"Failed to create like notification: {noti_err}")

        return {"message": "Liked successfully", "like_id": like_id}
    except Exception as mongo_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {mongo_err}"
        )


@app.delete("/api/likes", status_code=status.HTTP_200_OK)
def unlike_content(request: schemas.LikeRequest, profile: models.Profile = Depends(get_current_profile)):
    """
    Unlikes a post, comment, reel, or story (deleted from MongoDB).
    """
    target_type = request.target_type.lower()
    if target_type not in ["post", "comment", "reel", "story"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target_type."
        )

    try:
        deleted = mongodb.remove_like(
            profile_id=profile.profile_id,
            target_id=request.target_id,
            target_type=target_type
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Like not found"
            )
        return {"message": "Unliked successfully"}
    except HTTPException as http_ex:
        raise http_ex
    except Exception as mongo_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {mongo_err}"
        )


@app.get("/api/likes")
def get_content_likes(
    target_id: int = Query(..., description="ID of target to query"),
    target_type: str = Query(..., description="Must be 'post', 'comment', 'reel', or 'story'")
):
    """
    Retrieves likes list for a target from MongoDB.
    """
    target_type = target_type.lower()
    if target_type not in ["post", "comment", "reel", "story"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target_type. Must be 'post', 'comment', 'reel', or 'story'."
        )

    try:
        likes = mongodb.get_likes_for_target(target_id, target_type)
        # Format BSON ObjectId and datetimes to be JSON serializable
        formatted_likes = []
        for like in likes:
            formatted_likes.append({
                "like_id": str(like["_id"]),
                "profile_id": str(like["profile_id"]),
                "target_id": str(like["target_id"]),
                "target_type": like["target_type"],
                "liked_at": like["liked_at"].isoformat()
            })
        return formatted_likes
    except Exception as mongo_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MongoDB error: {mongo_err}"
        )


# ---------------------------------------------------------------------------
# Social Graph Routes
# ---------------------------------------------------------------------------

@app.post("/api/follow/{username}", status_code=status.HTTP_200_OK)
def follow_profile(username: str, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Follows a user directly if public, or sends a follow request if private.
    """
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile to follow not found")

    if target_profile.profile_id == profile.profile_id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    # Check if target profile blocked current user (or vice versa)
    if crud_social.is_blocked(db, profile.profile_id, target_profile.profile_id):
        raise HTTPException(status_code=403, detail="Cannot follow this profile")

    # If target profile is private, create a follow request
    if target_profile.is_private:
        req = crud_social.create_follow_request(db, profile.profile_id, target_profile.profile_id)
        return {"status": "pending", "message": "Follow request sent successfully", "request_id": str(req.request_id)}
    else:
        # Otherwise follow immediately
        crud_social.follow_profile(db, profile.profile_id, target_profile.profile_id)
        return {"status": "following", "message": "Followed user successfully"}


@app.post("/api/unfollow/{username}", status_code=status.HTTP_200_OK)
def unfollow_profile(username: str, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Unfollows a user.
    """
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile to unfollow not found")

    deleted = crud_social.unfollow_profile(db, profile.profile_id, target_profile.profile_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="You are not following this user")

    return {"message": "Unfollowed user successfully"}


@app.get("/api/follow/requests", response_model=List[schemas.FollowRequestResponse])
def get_pending_follow_requests(profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Lists received pending follow requests.
    """
    return crud_social.get_pending_requests(db, profile.profile_id)


@app.post("/api/follow/requests/{request_id}/respond", status_code=status.HTTP_200_OK)
def respond_follow_request(
    request_id: int,
    accept: bool = Query(..., description="Set true to accept, false to reject"),
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Responds (accept/reject) to a received follow request.
    """
    req = crud_social.respond_to_follow_request(db, request_id, profile.profile_id, accept)
    if not req:
        raise HTTPException(status_code=404, detail="Pending follow request not found")

    action = "accepted" if accept else "rejected"
    return {"message": f"Follow request successfully {action}"}


@app.post("/api/block/{username}", status_code=status.HTTP_200_OK)
def block_profile(username: str, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Blocks a user.
    """
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile to block not found")

    if target_profile.profile_id == profile.profile_id:
        raise HTTPException(status_code=400, detail="You cannot block yourself")

    crud_social.block_profile(db, profile.profile_id, target_profile.profile_id)
    return {"message": f"Successfully blocked {username}"}


@app.post("/api/unblock/{username}", status_code=status.HTTP_200_OK)
def unblock_profile(username: str, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Unblocks a user.
    """
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile to unblock not found")

    unblocked = crud_social.unblock_profile(db, profile.profile_id, target_profile.profile_id)
    if not unblocked:
        raise HTTPException(status_code=400, detail="You have not blocked this user")

    return {"message": f"Successfully unblocked {username}"}


@app.get("/api/{username}/followers", response_model=List[schemas.ProfileResponse])
def get_user_followers(username: str, db: Session = Depends(get_db)):
    """
    Lists followers of a profile.
    """
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return crud_social.get_followers(db, target_profile.profile_id)


@app.get("/api/{username}/following", response_model=List[schemas.ProfileResponse])
def get_user_following(username: str, db: Session = Depends(get_db)):
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return crud_social.get_following(db, target_profile.profile_id)


@app.get("/api/profiles/{username}", response_model=schemas.ProfileResponse)
def get_profile_by_username_endpoint(
    username: str,
    db: Session = Depends(get_db),
    current_profile: models.Profile = Depends(get_current_profile)
):
    """
    Retrieves profile details by username.
    """
    profile = crud_sql.get_profile_by_username(db, username)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@app.get("/api/profiles/{username}/posts", response_model=List[schemas.PostResponse])
def get_profile_posts_endpoint(username: str, db: Session = Depends(get_db)):
    """
    Retrieves posts published by a specific profile.
    """
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return crud_content.get_profile_posts(db, target_profile.profile_id)


@app.get("/api/profiles/{username}/reels", response_model=List[schemas.ReelResponse])
def get_profile_reels_endpoint(username: str, db: Session = Depends(get_db)):
    """
    Retrieves reels published by a specific profile.
    """
    target_profile = crud_sql.get_profile_by_username(db, username)
    if not target_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return crud_content.get_profile_reels(db, target_profile.profile_id)


# ---------------------------------------------------------------------------
# Content Management Routes
# ---------------------------------------------------------------------------

@app.post("/api/posts", response_model=schemas.PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(request: schemas.PostCreateRequest, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Creates a new post metadata in PostgreSQL.
    """
    return crud_content.create_post(db, profile.profile_id, request)


@app.get("/api/posts/feed", response_model=List[schemas.PostResponse])
def get_home_feed(profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Returns home feed posts from followed profiles and own posts.
    """
    return crud_content.get_feed_posts(db, profile.profile_id)


@app.get("/api/posts/{post_id}", response_model=schemas.PostResponse)
def get_post(post_id: int, db: Session = Depends(get_db)):
    """
    Retrieves a specific post.
    """
    post = crud_content.get_post_by_id(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.delete("/api/posts/{post_id}", status_code=status.HTTP_200_OK)
def delete_post(post_id: int, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Deletes a specific post owned by the caller.
    """
    deleted = crud_content.delete_post(db, post_id, profile.profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found or not owned by you")
    return {"message": "Post successfully deleted"}


@app.post("/api/posts/{post_id}/comments", response_model=schemas.CommentResponse, status_code=status.HTTP_201_CREATED)
def create_comment(
    post_id: int,
    request: schemas.CommentCreateRequest,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Creates a comment on a post.
    """
    post = crud_content.get_post_by_id(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return crud_content.create_post_comment(db, post_id, profile.profile_id, request)


@app.get("/api/posts/{post_id}/comments", response_model=List[schemas.CommentResponse])
def get_post_comments(post_id: int, db: Session = Depends(get_db)):
    """
    Lists comments on a post.
    """
    post = crud_content.get_post_by_id(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return crud_content.get_post_comments(db, post_id)


@app.post("/api/reels", response_model=schemas.ReelResponse, status_code=status.HTTP_201_CREATED)
def create_reel(request: schemas.ReelCreateRequest, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Creates a new reel.
    """
    return crud_content.create_reel(db, profile.profile_id, request)


@app.get("/api/reels", response_model=List[schemas.ReelResponse])
def get_reels(
    limit: int = Query(50, ge=1, le=100),
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Retrieves global reels feed.
    """
    return crud_content.get_reels_feed(db, limit)


@app.post("/api/reels/{reel_id}/comments", response_model=schemas.ReelCommentResponse, status_code=status.HTTP_201_CREATED)
def create_reel_comment_endpoint(
    reel_id: int,
    request: schemas.CommentCreateRequest,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Creates a comment on a reel.
    """
    reel = crud_content.get_reel_by_id(db, reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")
    return crud_content.create_reel_comment(db, reel_id, profile.profile_id, request.comment_text)


@app.get("/api/reels/{reel_id}/comments", response_model=List[schemas.ReelCommentResponse])
def get_reel_comments_endpoint(
    reel_id: int,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Lists comments on a reel.
    """
    reel = crud_content.get_reel_by_id(db, reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")
    return crud_content.get_reel_comments(db, reel_id)



@app.post("/api/stories", response_model=schemas.StoryResponse, status_code=status.HTTP_201_CREATED)
def create_story(request: schemas.StoryCreateRequest, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Creates a story (with optional media URL) that will automatically expire in 24 hours.
    """
    return crud_content.create_story(db, profile.profile_id, request)


@app.get("/api/stories/active", response_model=List[schemas.StoryResponse])
def get_active_stories(profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Retrieves unexpired stories from accounts followed by the current user.
    """
    return crud_content.get_active_stories_for_following(db, profile.profile_id)


@app.post("/api/stories/{story_id}/view", status_code=status.HTTP_200_OK)
def view_story(story_id: int, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Records a story view.
    """
    # Check if story exists
    story = db.query(models.Story).filter(models.Story.story_id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    
    crud_content.create_story_view(db, story_id, profile.profile_id)
    return {"message": "Story view successfully recorded"}


# ---------------------------------------------------------------------------
# Direct Messaging (DM) Routes
# ---------------------------------------------------------------------------

@app.post("/api/conversations", response_model=schemas.ConversationResponse, status_code=status.HTTP_201_CREATED)
def get_or_create_conversation(
    recipient_username: str = Query(..., description="Username of recipient"),
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Fetches or creates a direct chat conversation between current user and recipient.
    """
    recipient = crud_sql.get_profile_by_username(db, recipient_username)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient profile not found")

    if recipient.profile_id == profile.profile_id:
        raise HTTPException(status_code=400, detail="Cannot start a conversation with yourself")

    conv = crud_messaging.get_or_create_direct_conversation(db, profile.profile_id, recipient.profile_id)
    
    last_msg = db.query(models.Message).filter(models.Message.conversation_id == conv.conversation_id).order_by(models.Message.sent_at.desc()).first()
    last_message_content = last_msg.content if last_msg else None

    return schemas.ConversationResponse(
        conversation_id=conv.conversation_id,
        conversation_type=conv.conversation_type,
        created_at=conv.created_at,
        recipient_username=recipient_username,
        recipient_avatar=recipient.profile_picture,
        last_message=last_message_content
    )


@app.post("/api/conversations/group", response_model=schemas.ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    request: schemas.GroupConversationCreateRequest,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Creates a new group conversation.
    """
    conv = crud_messaging.create_group_conversation(db, profile.profile_id, request)
    
    member_usernames = []
    for member in conv.members:
        member_profile = db.query(models.Profile).filter(models.Profile.profile_id == member.profile_id).first()
        if member_profile:
            member_usernames.append(member_profile.username)
            
    return schemas.ConversationResponse(
        conversation_id=conv.conversation_id,
        conversation_type=conv.conversation_type,
        created_at=conv.created_at,
        name=conv.name,
        member_usernames=member_usernames
    )


@app.get("/api/conversations", response_model=List[schemas.ConversationResponse])
def list_conversations(profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Lists conversations the current profile is a member of.
    """
    conversations = crud_messaging.get_profile_conversations(db, profile.profile_id)
    response = []
    for conv in conversations:
        recipient_username = None
        recipient_avatar = None
        member_usernames = []
        
        # Get all members
        members = db.query(models.ConversationMember).filter(
            models.ConversationMember.conversation_id == conv.conversation_id
        ).all()
        for member in members:
            member_profile = db.query(models.Profile).filter(models.Profile.profile_id == member.profile_id).first()
            if member_profile:
                member_usernames.append(member_profile.username)
                if conv.conversation_type == "direct" and member.profile_id != profile.profile_id:
                    recipient_username = member_profile.username
                    recipient_avatar = member_profile.profile_picture

        last_msg = db.query(models.Message).filter(models.Message.conversation_id == conv.conversation_id).order_by(models.Message.sent_at.desc()).first()
        last_message_content = last_msg.content if last_msg else None

        response.append(schemas.ConversationResponse(
            conversation_id=conv.conversation_id,
            conversation_type=conv.conversation_type,
            created_at=conv.created_at,
            name=conv.name,
            recipient_username=recipient_username,
            recipient_avatar=recipient_avatar,
            last_message=last_message_content,
            member_usernames=member_usernames
        ))
    return response


@app.post("/api/conversations/{conv_id}/messages", response_model=schemas.MessageResponse, status_code=status.HTTP_201_CREATED)
def send_message(
    conv_id: int,
    request: schemas.MessageCreateRequest,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Sends a message in a conversation.
    """
    # Verify caller is a member of conversation
    is_member = db.query(models.ConversationMember).filter(
        models.ConversationMember.conversation_id == conv_id,
        models.ConversationMember.profile_id == profile.profile_id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="You are not a member of this conversation")

    msg = crud_messaging.send_message(db, conv_id, profile.profile_id, request)
    return schemas.MessageResponse(
        message_id=msg.message_id,
        conversation_id=msg.conversation_id,
        sender_id=msg.sender_id,
        message_type=msg.message_type,
        content=msg.content,
        sent_at=msg.sent_at,
        sender_username=profile.username,
        sender_avatar=profile.profile_picture
    )


@app.get("/api/conversations/{conv_id}/messages", response_model=List[schemas.MessageResponse])
def list_messages(
    conv_id: int,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Retrieves message history for a conversation.
    """
    is_member = db.query(models.ConversationMember).filter(
        models.ConversationMember.conversation_id == conv_id,
        models.ConversationMember.profile_id == profile.profile_id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="You are not a member of this conversation")

    messages = crud_messaging.get_conversation_messages(db, conv_id)
    response = []
    for msg in messages:
        sender_profile = db.query(models.Profile).filter(models.Profile.profile_id == msg.sender_id).first()
        sender_username = sender_profile.username if sender_profile else "unknown"
        sender_avatar = sender_profile.profile_picture if sender_profile else None
        response.append(schemas.MessageResponse(
            message_id=msg.message_id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            message_type=msg.message_type,
            content=msg.content,
            sent_at=msg.sent_at,
            sender_username=sender_username,
            sender_avatar=sender_avatar
        ))
    return response


@app.post("/api/messages/{msg_id}/seen", status_code=status.HTTP_200_OK)
def mark_message_seen(msg_id: int, profile: models.Profile = Depends(get_current_profile), db: Session = Depends(get_db)):
    """
    Marks a message as read/seen.
    """
    msg = db.query(models.Message).filter(models.Message.message_id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Verify caller is a member of the conversation the message belongs to
    is_member = db.query(models.ConversationMember).filter(
        models.ConversationMember.conversation_id == msg.conversation_id,
        models.ConversationMember.profile_id == profile.profile_id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="Forbidden")

    crud_messaging.mark_messages_as_seen(db, msg.conversation_id, [msg_id], profile.profile_id)
    return {"message": "Message marked as seen"}


@app.post("/api/messages/{msg_id}/react", status_code=status.HTTP_200_OK)
def react_to_message(
    msg_id: int,
    request: schemas.ReactionRequest,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Reacts to a message with an emoji.
    """
    msg = db.query(models.Message).filter(models.Message.message_id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    is_member = db.query(models.ConversationMember).filter(
        models.ConversationMember.conversation_id == msg.conversation_id,
        models.ConversationMember.profile_id == profile.profile_id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="Forbidden")

    react = crud_messaging.add_message_reaction(db, msg_id, profile.profile_id, request.emoji)
    return {"message": "Reaction added successfully", "emoji": react.emoji}


# ---------------------------------------------------------------------------
# File Upload, Search, Notifications, and Real-time WebSockets
# ---------------------------------------------------------------------------

@app.post("/api/upload")
def upload_file(
    file: UploadFile = File(...),
    profile: models.Profile = Depends(get_current_profile)
):
    """
    Saves a multipart file upload to static/uploads and returns its path.
    """
    upload_dir = "static/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"url": f"/static/uploads/{filename}"}


@app.get("/api/notifications", response_model=List[schemas.NotificationResponse])
def list_notifications(
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Retrieves the user's notifications.
    """
    from crud import crud_notifications
    return crud_notifications.get_notifications(db, profile.profile_id)


@app.put("/api/notifications/{noti_id}/read")
def mark_notification_as_read(
    noti_id: int,
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Marks a specific notification as read.
    """
    from crud import crud_notifications
    success = crud_notifications.mark_notification_read(db, noti_id, profile.profile_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Notification marked as read"}


@app.get("/api/search", response_model=schemas.SearchResultResponse)
def search_platform(
    q: str = Query(..., min_length=1),
    profile: models.Profile = Depends(get_current_profile),
    db: Session = Depends(get_db)
):
    """
    Performs a global search across users, posts, reels, and hashtags.
    """
    from crud import crud_search
    return crud_search.global_search(db, q)


@app.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Handles persistent WebSocket connection for real-time messaging and alerts.
    """
    from dependencies import ws_manager
    profile = crud_sql.authenticate_access_token(db, token)
    if not profile or profile.user.status == "suspended":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    profile_id = profile.profile_id
    await ws_manager.connect(profile_id, websocket)
    try:
        while True:
            # Maintain connection, handle client events
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(profile_id)
