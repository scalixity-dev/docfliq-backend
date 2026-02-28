"""Hashtag endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HashtagItem(BaseModel):
    """Single hashtag with usage count."""

    name: str = Field(description="Lowercase hashtag (without '#' prefix).")
    post_count: int = Field(description="Number of posts using this hashtag in the time window.")


class TrendingHashtagsResponse(BaseModel):
    """Response for trending hashtags endpoint."""

    items: list[HashtagItem]
    window_hours: int = Field(description="Time window in hours used for the count.")


class HashtagSuggestResponse(BaseModel):
    """Response for hashtag autocomplete."""

    suggestions: list[HashtagItem]
