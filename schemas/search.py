# pyrefly: ignore [missing-import]
from pydantic import BaseModel
from typing import List, Dict, Any
from .user import ProfileResponse
from .content import PostResponse, ReelResponse

class SearchResultResponse(BaseModel):
    profiles: List[ProfileResponse]
    posts: List[PostResponse]
    reels: List[ReelResponse]
    hashtags: List[Dict[str, Any]]
