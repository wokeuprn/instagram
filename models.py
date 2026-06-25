# pyrefly: ignore [missing-import]
import sqlalchemy
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import relationship
from database import Base


# ---------------------------------------------------------------------------
# Users & Profiles
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    user_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    full_name = sqlalchemy.Column(sqlalchemy.String)
    email = sqlalchemy.Column(sqlalchemy.String, unique=True)
    phone = sqlalchemy.Column(sqlalchemy.String)
    status = sqlalchemy.Column(sqlalchemy.String)
    is_email_verified = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    is_phone_verified = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)
    last_login = sqlalchemy.Column(sqlalchemy.DateTime)

    # Relationships
    # profile = relationship("Profile", back_populates="user", uselist=False, foreign_keys="[Profile.user_id]")


class Profile(Base):
    __tablename__ = "profiles"

    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("users.user_id"), unique=True)
    username = sqlalchemy.Column(sqlalchemy.String, unique=True)
    password = sqlalchemy.Column(sqlalchemy.String)
    full_name = sqlalchemy.Column(sqlalchemy.String)
    bio = sqlalchemy.Column(sqlalchemy.Text)
    profile_picture = sqlalchemy.Column(sqlalchemy.String)
    website = sqlalchemy.Column(sqlalchemy.String)
    account_type = sqlalchemy.Column(sqlalchemy.String)
    is_private = sqlalchemy.Column(sqlalchemy.Boolean)
    verified_status = sqlalchemy.Column(sqlalchemy.Boolean)
    failed_login_attempts = sqlalchemy.Column(sqlalchemy.Integer, default=0)
    lockout_until = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)

    # Relationships
    # user = relationship("User", back_populates="profile", foreign_keys=[user_id])
    stats = relationship("ProfileStats", back_populates="profile", uselist=False)
    posts = relationship("Post", back_populates="profile")
    reels = relationship("Reel", back_populates="profile")
    stories = relationship("Story", back_populates="profile")
    highlights = relationship("Highlight", back_populates="profile")
    notes = relationship("Note", back_populates="profile")
    access_tokens = relationship("AccessToken", back_populates="profile")
    refresh_tokens = relationship("RefreshToken", back_populates="profile")


class ProfileStats(Base):
    __tablename__ = "profile_stats"

    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"), primary_key=True)
    followers_count = sqlalchemy.Column(sqlalchemy.Integer)
    following_count = sqlalchemy.Column(sqlalchemy.Integer)
    posts_count = sqlalchemy.Column(sqlalchemy.Integer)
    reels_count = sqlalchemy.Column(sqlalchemy.Integer)

    profile = relationship("Profile", back_populates="stats")





# ---------------------------------------------------------------------------
# Social Graph
# ---------------------------------------------------------------------------

class Follow(Base):
    __tablename__ = "follows"

    follower_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    following_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    followed_at = sqlalchemy.Column(sqlalchemy.DateTime)

    __table_args__ = (
        sqlalchemy.PrimaryKeyConstraint("follower_id", "following_id"),
    )


class FollowRequest(Base):
    __tablename__ = "follow_requests"

    request_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    sender_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    receiver_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    status = sqlalchemy.Column(sqlalchemy.String)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)


class Block(Base):
    __tablename__ = "blocks"

    blocker_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    blocked_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    blocked_at = sqlalchemy.Column(sqlalchemy.DateTime)

    __table_args__ = (
        sqlalchemy.PrimaryKeyConstraint("blocker_id", "blocked_id"),
    )


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

class Post(Base):
    __tablename__ = "posts"

    post_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    caption = sqlalchemy.Column(sqlalchemy.Text)
    location = sqlalchemy.Column(sqlalchemy.String)
    visibility = sqlalchemy.Column(sqlalchemy.String)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)

    profile = relationship("Profile", back_populates="posts")
    comments = relationship("PostComment", back_populates="post")
    hashtags = relationship("PostHashtag", back_populates="post")
    search_index = relationship("PostSearchIndex", back_populates="post", uselist=False)


class PostComment(Base):
    __tablename__ = "post_comments"

    comment_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    post_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("posts.post_id"))
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    comment_text = sqlalchemy.Column(sqlalchemy.Text)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)

    post = relationship("Post", back_populates="comments")


# Reels

class Reel(Base):
    __tablename__ = "reels"

    reel_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    caption = sqlalchemy.Column(sqlalchemy.Text)
    duration = sqlalchemy.Column(sqlalchemy.Integer)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)

    profile = relationship("Profile", back_populates="reels")
    comments = relationship("ReelComment", back_populates="reel")
    hashtags = relationship("ReelHashtag", back_populates="reel")
    audio = relationship("ReelAudio", back_populates="reel", uselist=False)
    search_index = relationship("ReelSearchIndex", back_populates="reel", uselist=False)


class ReelComment(Base):
    __tablename__ = "reel_comments"

    reel_comment_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    reel_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("reels.reel_id"))
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    comment_text = sqlalchemy.Column(sqlalchemy.Text)

    reel = relationship("Reel", back_populates="comments")


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------

class Story(Base):
    __tablename__ = "stories"

    story_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    expires_at = sqlalchemy.Column(sqlalchemy.DateTime)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)

    profile = relationship("Profile", back_populates="stories")
    views = relationship("StoryView", back_populates="story")
    reactions = relationship("StoryReaction", back_populates="story")
    comments = relationship("StoryComment", back_populates="story")


class StoryView(Base):
    __tablename__ = "story_views"

    story_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("stories.story_id"), primary_key=True)
    viewer_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"), primary_key=True)
    viewed_at = sqlalchemy.Column(sqlalchemy.DateTime)

    story = relationship("Story", back_populates="views")


class StoryReaction(Base):
    __tablename__ = "story_reactions"

    reaction_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    story_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("stories.story_id"))
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    emoji = sqlalchemy.Column(sqlalchemy.String)

    story = relationship("Story", back_populates="reactions")


class StoryComment(Base):
    __tablename__ = "story_comments"

    comment_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    story_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("stories.story_id"))
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    comment_text = sqlalchemy.Column(sqlalchemy.Text)

    story = relationship("Story", back_populates="comments")


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

class Highlight(Base):
    __tablename__ = "highlights"

    highlight_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    title = sqlalchemy.Column(sqlalchemy.String)
    cover_image = sqlalchemy.Column(sqlalchemy.String)

    profile = relationship("Profile", back_populates="highlights")
    stories = relationship("HighlightStory", back_populates="highlight")


class HighlightStory(Base):
    __tablename__ = "highlight_stories"

    highlight_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("highlights.highlight_id"))
    story_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("stories.story_id"))

    __table_args__ = (
        sqlalchemy.PrimaryKeyConstraint("highlight_id", "story_id"),
    )

    highlight = relationship("Highlight", back_populates="stories")


# ---------------------------------------------------------------------------
# Saved / Collections
# ---------------------------------------------------------------------------

class Saved(Base):
    __tablename__ = "saved"

    saved_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    post_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("posts.post_id"))
    reel_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("reels.reel_id"))
    audio_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("audio_tracks.audio_id"))


class SaveCollection(Base):
    __tablename__ = "save_collections"

    collection_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    saved_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("saved.saved_id"))
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    collection_name = sqlalchemy.Column(sqlalchemy.String)

    saved_posts = relationship("SavedPost", back_populates="collection")
    saved_reels = relationship("SavedReel", back_populates="collection")


class SavedPost(Base):
    __tablename__ = "saved_posts"

    saved_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("saved.saved_id"), primary_key=True)
    collection_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("save_collections.collection_id"))
    post_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("posts.post_id"))
    saved_at = sqlalchemy.Column(sqlalchemy.DateTime)

    collection = relationship("SaveCollection", back_populates="saved_posts")


class SavedReel(Base):
    __tablename__ = "saved_reels"

    saved_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("saved.saved_id"), primary_key=True)
    collection_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("save_collections.collection_id"))
    reel_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("reels.reel_id"))
    saved_at = sqlalchemy.Column(sqlalchemy.DateTime)

    collection = relationship("SaveCollection", back_populates="saved_reels")


# ---------------------------------------------------------------------------
# Hashtags
# ---------------------------------------------------------------------------

class Hashtag(Base):
    __tablename__ = "hashtags"

    hashtag_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    tag_name = sqlalchemy.Column(sqlalchemy.String, unique=True)

    posts = relationship("PostHashtag", back_populates="hashtag")
    reels = relationship("ReelHashtag", back_populates="hashtag")
    search_index = relationship("HashtagSearchIndex", back_populates="hashtag", uselist=False)


class PostHashtag(Base):
    __tablename__ = "post_hashtags"

    post_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("posts.post_id"), primary_key=True)
    hashtag_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("hashtags.hashtag_id"), primary_key=True)

    post = relationship("Post", back_populates="hashtags")
    hashtag = relationship("Hashtag", back_populates="posts")


class ReelHashtag(Base):
    __tablename__ = "reel_hashtags"

    reel_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("reels.reel_id"), primary_key=True)
    hashtag_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("hashtags.hashtag_id"), primary_key=True)

    reel = relationship("Reel", back_populates="hashtags")
    hashtag = relationship("Hashtag", back_populates="reels")


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    conversation_type = sqlalchemy.Column(sqlalchemy.String)
    created_at = sqlalchemy.Column(sqlalchemy.DateTime)
    name = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    last_message_at = sqlalchemy.Column(sqlalchemy.DateTime, default=sqlalchemy.func.now())

    members = relationship("ConversationMember", back_populates="conversation")
    messages = relationship("Message", back_populates="conversation")


class ConversationMember(Base):
    __tablename__ = "conversation_members"

    conversation_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("conversations.conversation_id"), primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"), primary_key=True)
    joined_at = sqlalchemy.Column(sqlalchemy.DateTime)

    conversation = relationship("Conversation", back_populates="members")


class Message(Base):
    __tablename__ = "messages"

    message_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    conversation_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("conversations.conversation_id"))
    sender_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    message_type = sqlalchemy.Column(sqlalchemy.String)
    content = sqlalchemy.Column(sqlalchemy.Text)
    sent_at = sqlalchemy.Column(sqlalchemy.DateTime)

    conversation = relationship("Conversation", back_populates="messages")
    reactions = relationship("MessageReaction", back_populates="message")
    seen_by = relationship("MessageSeen", back_populates="message")


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    reaction_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    message_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("messages.message_id"))
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    emoji = sqlalchemy.Column(sqlalchemy.String)

    message = relationship("Message", back_populates="reactions")


class MessageSeen(Base):
    __tablename__ = "message_seen"

    message_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("messages.message_id"), primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"), primary_key=True)
    seen_at = sqlalchemy.Column(sqlalchemy.DateTime)

    message = relationship("Message", back_populates="seen_by")


# ---------------------------------------------------------------------------
# Notes & Notifications
# ---------------------------------------------------------------------------

class Note(Base):
    __tablename__ = "notes"

    note_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    content = sqlalchemy.Column(sqlalchemy.String)
    expires_at = sqlalchemy.Column(sqlalchemy.DateTime)

    profile = relationship("Profile", back_populates="notes")


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    receiver_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    user_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    notification_type = sqlalchemy.Column(sqlalchemy.String)
    reference_id = sqlalchemy.Column(sqlalchemy.BigInteger)
    is_read = sqlalchemy.Column(sqlalchemy.Boolean)


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    audio_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    title = sqlalchemy.Column(sqlalchemy.String)
    artist = sqlalchemy.Column(sqlalchemy.String)

    reels = relationship("ReelAudio", back_populates="audio")
    search_index = relationship("AudioSearchIndex", back_populates="audio", uselist=False)


class ReelAudio(Base):
    __tablename__ = "reel_audio"

    reel_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("reels.reel_id"), primary_key=True)
    audio_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("audio_tracks.audio_id"), primary_key=True)

    reel = relationship("Reel", back_populates="audio")
    audio = relationship("AudioTrack", back_populates="reels")


# ---------------------------------------------------------------------------
# Search Indexes
# ---------------------------------------------------------------------------

class UserSearchIndex(Base):
    __tablename__ = "user_search_index"

    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"), primary_key=True)
    searchable_text = sqlalchemy.Column(sqlalchemy.Text)


class PostSearchIndex(Base):
    __tablename__ = "post_search_index"

    post_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("posts.post_id"), primary_key=True)
    searchable_text = sqlalchemy.Column(sqlalchemy.Text)

    post = relationship("Post", back_populates="search_index")


class ReelSearchIndex(Base):
    __tablename__ = "reel_search_index"

    reel_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("reels.reel_id"), primary_key=True)
    searchable_text = sqlalchemy.Column(sqlalchemy.Text)

    reel = relationship("Reel", back_populates="search_index")


class HashtagSearchIndex(Base):
    __tablename__ = "hashtag_search_index"

    hashtag_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("hashtags.hashtag_id"), primary_key=True)
    usage_count = sqlalchemy.Column(sqlalchemy.BigInteger)

    hashtag = relationship("Hashtag", back_populates="search_index")


class AudioSearchIndex(Base):
    __tablename__ = "audio_search_index"

    audio_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("audio_tracks.audio_id"), primary_key=True)
    usage_count = sqlalchemy.Column(sqlalchemy.BigInteger)

    audio = relationship("AudioTrack", back_populates="search_index")





class TrendingSearch(Base):
    __tablename__ = "trending_searches"

    trend_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    keyword = sqlalchemy.Column(sqlalchemy.String)
    search_count = sqlalchemy.Column(sqlalchemy.BigInteger)


# ---------------------------------------------------------------------------
# Auth Tokens
# ---------------------------------------------------------------------------

class AccessToken(Base):
    __tablename__ = "access_tokens"

    access_token_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    issued_at = sqlalchemy.Column(sqlalchemy.DateTime)
    expires_at = sqlalchemy.Column(sqlalchemy.DateTime)
    revoked = sqlalchemy.Column(sqlalchemy.Boolean)

    profile = relationship("Profile", back_populates="access_tokens")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    refresh_token_id = sqlalchemy.Column(sqlalchemy.BigInteger, primary_key=True)
    profile_id = sqlalchemy.Column(sqlalchemy.BigInteger, sqlalchemy.ForeignKey("profiles.profile_id"))
    token = sqlalchemy.Column(sqlalchemy.String, unique=True)
    issued_at = sqlalchemy.Column(sqlalchemy.DateTime)
    expires_at = sqlalchemy.Column(sqlalchemy.DateTime)
    revoked = sqlalchemy.Column(sqlalchemy.Boolean)
    revoked_at = sqlalchemy.Column(sqlalchemy.DateTime)

    profile = relationship("Profile", back_populates="refresh_tokens")
