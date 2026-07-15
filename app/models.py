from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def parse_json_object(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


@dataclass(slots=True)
class Place:
    id: int
    content_id: str
    content_type_id: str
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
    source_modified_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Place":
        return cls(
            id=int(row["id"]),
            content_id=str(row["content_id"]),
            content_type_id=str(row["content_type_id"]),
            region=str(row["region"]),
            category=str(row["category"]),
            title=str(row["title"]),
            address=str(row["address"]),
            address_detail=str(row["address_detail"]),
            telephone=str(row["telephone"]),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            image_url=str(row["image_url"]),
            thumbnail_url=str(row["thumbnail_url"]),
            source_modified_at=str(row["source_modified_at"]),
        )


@dataclass(slots=True)
class Comment:
    id: int
    post_id: int
    author_nickname: str
    body: str
    password_hash: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Comment":
        return cls(
            id=int(row["id"]),
            post_id=int(row["post_id"]),
            author_nickname=str(row["author_nickname"]),
            body=str(row["body"]),
            password_hash=str(row["password_hash"]),
            created_at=parse_datetime(row["created_at"]),
        )


@dataclass(slots=True)
class Post:
    id: int
    title: str
    body: str
    author_nickname: str
    password_hash: str
    region: str
    tags: list[str]
    itinerary: dict[str, Any] | None
    view_count: int
    created_at: datetime
    updated_at: datetime
    comments: list[Comment] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: sqlite3.Row, comments: list[Comment] | None = None) -> "Post":
        return cls(
            id=int(row["id"]),
            title=str(row["title"]),
            body=str(row["body"]),
            author_nickname=str(row["author_nickname"]),
            password_hash=str(row["password_hash"]),
            region=str(row["region"]),
            tags=parse_json_list(row["tags_json"]),
            itinerary=parse_json_object(row["itinerary_json"]),
            view_count=int(row["view_count"]),
            created_at=parse_datetime(row["created_at"]),
            updated_at=parse_datetime(row["updated_at"]),
            comments=comments or [],
        )
