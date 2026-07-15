from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_settings


settings = get_settings()


def connect_database(path: Path | None = None) -> sqlite3.Connection:
    database_path = path or settings.resolved_database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        database_path,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@contextmanager
def database_connection(path: Path | None = None):
    connection = connect_database(path)
    try:
        yield connection
    finally:
        connection.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    connection = connect_database()
    try:
        yield connection
    finally:
        connection.close()


def init_db(*, drop_existing: bool = False, path: Path | None = None) -> None:
    with database_connection(path) as db:
        if drop_existing:
            db.executescript(
                """
                DROP TABLE IF EXISTS comments;
                DROP TABLE IF EXISTS posts;
                DROP TABLE IF EXISTS places;
                """
            )

        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS places (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id TEXT NOT NULL UNIQUE,
                content_type_id TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                address_detail TEXT NOT NULL DEFAULT '',
                telephone TEXT NOT NULL DEFAULT '',
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                image_url TEXT NOT NULL DEFAULT '',
                thumbnail_url TEXT NOT NULL DEFAULT '',
                source_modified_at TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS ix_places_content_id
                ON places(content_id);
            CREATE INDEX IF NOT EXISTS ix_places_region
                ON places(region);
            CREATE INDEX IF NOT EXISTS ix_places_category
                ON places(category);
            CREATE INDEX IF NOT EXISTS ix_places_title
                ON places(title);
            CREATE INDEX IF NOT EXISTS ix_places_region_category
                ON places(region, category);

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                author_nickname TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                region TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                itinerary_json TEXT,
                view_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_posts_title
                ON posts(title);
            CREATE INDEX IF NOT EXISTS ix_posts_region
                ON posts(region);
            CREATE INDEX IF NOT EXISTS ix_posts_created_at
                ON posts(created_at DESC);

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                author_nickname TEXT NOT NULL,
                body TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_comments_post_id
                ON comments(post_id);
            CREATE INDEX IF NOT EXISTS ix_comments_created_at
                ON comments(created_at);
            """
        )
        db.commit()
