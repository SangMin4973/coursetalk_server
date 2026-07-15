from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlaceOut(BaseModel):
    id: int
    content_id: str
    region: str
    category: str
    title: str
    address: str
    address_detail: str
    telephone: str
    latitude: float
    longitude: float
    image_url: str
    thumbnail_url: str

    model_config = ConfigDict(from_attributes=True)


class ItineraryRequest(BaseModel):
    region: str = Field(default="광주_전라권", min_length=1, max_length=40)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    companion: str = Field(min_length=1, max_length=30)
    preferences: list[str] = Field(min_length=1, max_length=6)
    extra_request: str = Field(default="", max_length=500)

    @field_validator("preferences")
    @classmethod
    def normalize_preferences(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            item = item.strip()
            if item and item not in cleaned:
                cleaned.append(item)
        if not cleaned:
            raise ValueError("선호 카테고리를 하나 이상 선택해 주세요.")
        return cleaned


class ItineraryStop(BaseModel):
    order: int
    place: PlaceOut
    start_time: str
    end_time: str
    stay_minutes: int
    travel_minutes_from_previous: int
    reason: str


class ShareDraft(BaseModel):
    title: str
    body: str
    tags: list[str]


class ItineraryResponse(BaseModel):
    title: str
    summary: str
    region: str
    companion: str
    preferences: list[str]
    source: str
    stops: list[ItineraryStop]
    warnings: list[str] = []
    share_draft: ShareDraft


class AISelectedStop(BaseModel):
    place_id: int
    duration_minutes: int = Field(ge=30, le=180)
    reason: str = Field(min_length=3, max_length=160)


class AIPlanSelection(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    summary: str = Field(min_length=5, max_length=250)
    stops: list[AISelectedStop] = Field(min_length=2, max_length=5)


class PostCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=5, max_length=10000)
    author_nickname: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=4, max_length=100)
    region: str = Field(default="광주_전라권", min_length=1, max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=10)
    itinerary: dict[str, Any] | None = None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        cleaned = []
        for tag in value:
            tag = tag.strip().lstrip("#")[:30]
            if tag and tag not in cleaned:
                cleaned.append(tag)
        return cleaned[:10]


class PostUpdate(BaseModel):
    password: str = Field(min_length=4, max_length=100)
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=5, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=10)


class PasswordCheck(BaseModel):
    password: str = Field(min_length=4, max_length=100)


class CommentCreate(BaseModel):
    author_nickname: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=4, max_length=100)
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    post_id: int
    author_nickname: str
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostListItem(BaseModel):
    id: int
    title: str
    body_preview: str
    author_nickname: str
    region: str
    tags: list[str]
    view_count: int
    comment_count: int
    created_at: datetime


class PostListResponse(BaseModel):
    items: list[PostListItem]
    total: int
    page: int
    size: int


class PostDetail(BaseModel):
    id: int
    title: str
    body: str
    author_nickname: str
    region: str
    tags: list[str]
    itinerary: dict[str, Any] | None
    view_count: int
    created_at: datetime
    updated_at: datetime
    comments: list[CommentOut]
