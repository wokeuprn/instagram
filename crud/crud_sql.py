import os
import sys
from datetime import datetime, timedelta
import secrets
from typing import Optional

# Add project root to sys.path to allow direct execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from sqlalchemy import or_

from database import models
import auth
import schemas


# ---------------------------------------------------------------------------
# Query Helpers
# ---------------------------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()


def get_profile_by_username(db: Session, username: str) -> Optional[models.Profile]:
    return db.query(models.Profile).filter(models.Profile.username == username).first()


def get_profile_by_id(db: Session, profile_id: int) -> Optional[models.Profile]:
    return db.query(models.Profile).filter(models.Profile.profile_id == profile_id).first()



# Registration and Profile Management

def create_user_and_profile(db: Session, request: schemas.UserRegisterRequest) -> models.Profile:
    """
    Creates a new User and associated Profile in a single transaction.
    Passwords are securely hashed.
    """
    # 1. Create User
    db_user = models.User(
        full_name=request.full_name,
        email=request.email,
        phone=request.phone,
        status="active",
        is_email_verified=False,
        is_phone_verified=False,
        created_at=datetime.utcnow(),
        last_login=None
    )
    db.add(db_user)
    db.flush()  

    hashed_password = auth.hash_password(request.password)

    # Create Profile
    db_profile = models.Profile(
        user_id=db_user.user_id,
        username=request.username,
        password=hashed_password,
        full_name=request.full_name,
        bio=None,
        profile_picture=None,
        website=None,
        account_type="personal",
        is_private=False,
        verified_status=False,
        failed_login_attempts=0,
        lockout_until=None
    )
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)

    # Index User Profile for search
    try:
        from .crud_search import index_user_profile
        index_user_profile(db, db_profile.profile_id)
    except Exception as search_err:
        print(f"Failed to index user: {search_err}")

    return db_profile


def update_profile(
    db: Session, 
    profile_id: int, 
    request: schemas.ProfileEditRequest
) -> models.Profile:
    """
    Updates profile fields (website, bio, username) and linked user fields (full_name, phone).
    """
    db_profile = get_profile_by_id(db, profile_id)
    if not db_profile:
        raise ValueError("Profile not found")

    db_user = db_profile.user

    # Update User attributes
    if request.full_name is not None:
        db_user.full_name = request.full_name
        db_profile.full_name = request.full_name
    if request.phone is not None:
        db_user.phone = request.phone

    # Update Profile attributes
    if request.bio is not None:
        db_profile.bio = request.bio
    if request.website is not None:
        db_profile.website = request.website
    if request.username is not None:
        db_profile.username = request.username
    if hasattr(request, "profile_picture") and request.profile_picture is not None:
        db_profile.profile_picture = request.profile_picture

    db.commit()
    db.refresh(db_profile)

    # Reindex User Profile for search
    try:
        from .crud_search import index_user_profile
        index_user_profile(db, db_profile.profile_id)
    except Exception as search_err:
        print(f"Failed to reindex user: {search_err}")

    return db_profile


def verify_user_email(db: Session, user_id: int) -> bool:
    db_user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if db_user:
        db_user.is_email_verified = True
        db.commit()
        return True
    return False


def verify_user_phone(db: Session, user_id: int) -> bool:
    db_user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if db_user:
        db_user.is_phone_verified = True
        db.commit()
        return True
    return False

# Authentication & Lockout Handling

def handle_login_attempt(db: Session, request: schemas.UserLoginRequest) -> models.Profile:
    """
    Verifies credentials and manages failed login attempts and lockout states.
    Raises ValueError with error details on failure.
    """
    # 1. Resolve Profile
    # Can log in using either username or email
    db_profile = db.query(models.Profile).join(models.User, models.Profile.user_id == models.User.user_id).filter(
        or_(
            models.Profile.username == request.username_or_email,
            models.User.email == request.username_or_email
        )
    ).first()

    if not db_profile:
        raise ValueError("Invalid username/email or password")

    # 1.5 Check User Suspension Status
    if db_profile.user.status == "suspended":
        raise ValueError("This account has been suspended.")

    # 2. Check Lockout Status
    if db_profile.lockout_until and db_profile.lockout_until > datetime.utcnow():
        remaining = db_profile.lockout_until - datetime.utcnow()
        minutes = int(remaining.total_seconds() // 60) + 1
        raise ValueError(f"Account locked. Try again in {minutes} minutes.")

    # 3. Verify Password
    if not auth.verify_password(request.password, db_profile.password):
        # Increment failed login attempts
        db_profile.failed_login_attempts += 1
        
        # Check if we should lockout (e.g., after 5 failed attempts)
        if db_profile.failed_login_attempts >= 5:
            db_profile.lockout_until = datetime.utcnow() + timedelta(minutes=15)
            db.commit()
            raise ValueError("Invalid credentials. Account locked for 15 minutes due to too many failed attempts.")
        
        db.commit()
        raise ValueError("Invalid username/email or password")

    # 4. Success: Reset rate limiting parameters & update last login
    db_profile.failed_login_attempts = 0
    db_profile.lockout_until = None
    db_profile.user.last_login = datetime.utcnow()
    db.commit()
    return db_profile

# Session & Token Management

def create_session_tokens(db: Session, profile_id: int) -> schemas.TokenResponse:
    """
    Creates an access token and refresh token record for a profile.
    Uses secure random 63-bit integer for access_token_id and random token string for RefreshToken.
    """
    # Create Access Token (expires in 1 hour)
    access_token_id = auth.generate_token_id()
    db_access = models.AccessToken(
        access_token_id=access_token_id,
        profile_id=profile_id,
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
        revoked=False
    )
    db.add(db_access)

    # Create Refresh Token (expires in 30 days)
    refresh_token_str = auth.generate_session_token()
    db_refresh = models.RefreshToken(
        profile_id=profile_id,
        token=refresh_token_str,
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=30),
        revoked=False,
        revoked_at=None
    )
    db.add(db_refresh)
    db.commit()

    return schemas.TokenResponse(
        access_token=str(access_token_id),
        refresh_token=refresh_token_str,
        token_type="bearer"
    )


def revoke_session_tokens(db: Session, profile_id: int) -> None:
    """
    Revokes all active tokens for a profile (on Logout).
    """
    # Revoke Access Tokens
    db.query(models.AccessToken).filter(
        models.AccessToken.profile_id == profile_id,
        models.AccessToken.revoked == False
    ).update({models.AccessToken.revoked: True}, synchronize_session=False)

    # Revoke Refresh Tokens
    db.query(models.RefreshToken).filter(
        models.RefreshToken.profile_id == profile_id,
        models.RefreshToken.revoked == False
    ).update({
        models.RefreshToken.revoked: True,
        models.RefreshToken.revoked_at: datetime.utcnow()
    }, synchronize_session=False)

    db.commit()


def authenticate_access_token(db: Session, access_token_str: str) -> Optional[models.Profile]:
    """
    Checks if the access token matches a valid database record, is not revoked, and is not expired.
    Returns the Profile model if authenticated successfully.
    """
    try:
        token_id = int(access_token_str)
    except ValueError:
        return None

    db_access = db.query(models.AccessToken).filter(
        models.AccessToken.access_token_id == token_id
    ).first()

    if not db_access:
        return None

    if db_access.revoked or db_access.expires_at < datetime.utcnow():
        return None

    return db_access.profile


def update_user_status(db: Session, user_id: int, status: str) -> Optional[models.User]:
    db_user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if db_user:
        db_user.status = status
        db.commit()
        db.refresh(db_user)
        return db_user
    return None


def update_profile_verification(db: Session, profile_id: int, verified_status: bool) -> Optional[models.Profile]:
    db_profile = db.query(models.Profile).filter(models.Profile.profile_id == profile_id).first()
    if db_profile:
        db_profile.verified_status = verified_status
        db.commit()
        db.refresh(db_profile)
        return db_profile
    return None
