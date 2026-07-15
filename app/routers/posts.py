from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.database import get_db
from app.models import Comment, Post, utc_now_iso
from app.schemas import (
    CommentCreate,
    CommentOut,
    PasswordCheck,
    PostCreate,
    PostDetail,
    PostListItem,
    PostListResponse,
    PostUpdate,
)
from app.services.security import hash_password, verify_password


router = APIRouter(tags=["community"])


def _post_detail(post: Post) -> PostDetail:
    return PostDetail(
        id=post.id,
        title=post.title,
        body=post.body,
        author_nickname=post.author_nickname,
        region=post.region,
        tags=post.tags,
        itinerary=post.itinerary,
        view_count=post.view_count,
        created_at=post.created_at,
        updated_at=post.updated_at,
        comments=[CommentOut.model_validate(comment) for comment in post.comments],
    )


def _load_post(db: sqlite3.Connection, post_id: int) -> Post | None:
    post_row = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post_row is None:
        return None
    comment_rows = db.execute(
        "SELECT * FROM comments WHERE post_id = ? ORDER BY created_at, id",
        (post_id,),
    ).fetchall()
    comments = [Comment.from_row(row) for row in comment_rows]
    return Post.from_row(post_row, comments)


@router.get("/posts", response_model=PostListResponse)
def list_posts(
    query: str = Query(default="", max_length=100),
    region: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    db: sqlite3.Connection = Depends(get_db),
):
    conditions: list[str] = []
    params: list[object] = []

    if query.strip():
        keyword = f"%{query.strip()}%"
        conditions.append("(p.title LIKE ? OR p.body LIKE ?)")
        params.extend([keyword, keyword])
    if region.strip():
        conditions.append("p.region = ?")
        params.append(region.strip())

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    total = int(
        db.execute(
            f"SELECT COUNT(*) AS count FROM posts p {where_sql}",
            params,
        ).fetchone()["count"]
    )

    list_params = [*params, size, (page - 1) * size]
    rows = db.execute(
        f"""
        SELECT
            p.*,
            (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
        FROM posts p
        {where_sql}
        ORDER BY p.created_at DESC, p.id DESC
        LIMIT ? OFFSET ?
        """,
        list_params,
    ).fetchall()

    items = []
    for row in rows:
        post = Post.from_row(row)
        items.append(
            PostListItem(
                id=post.id,
                title=post.title,
                body_preview=(post.body[:150] + "…") if len(post.body) > 150 else post.body,
                author_nickname=post.author_nickname,
                region=post.region,
                tags=post.tags,
                view_count=post.view_count,
                comment_count=int(row["comment_count"]),
                created_at=post.created_at,
            )
        )
    return PostListResponse(items=items, total=total, page=page, size=size)


@router.post("/posts", response_model=PostDetail, status_code=201)
def create_post(payload: PostCreate, db: sqlite3.Connection = Depends(get_db)):
    now = utc_now_iso()
    cursor = db.execute(
        """
        INSERT INTO posts (
            title, body, author_nickname, password_hash, region,
            tags_json, itinerary_json, view_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            payload.title.strip(),
            payload.body.strip(),
            payload.author_nickname.strip(),
            hash_password(payload.password),
            payload.region.strip(),
            json.dumps(payload.tags, ensure_ascii=False),
            json.dumps(payload.itinerary, ensure_ascii=False) if payload.itinerary is not None else None,
            now,
            now,
        ),
    )
    db.commit()
    post = _load_post(db, int(cursor.lastrowid))
    if post is None:
        raise HTTPException(status_code=500, detail="게시글 저장 후 조회에 실패했습니다.")
    return _post_detail(post)


@router.get("/posts/{post_id}", response_model=PostDetail)
def get_post(post_id: int, db: sqlite3.Connection = Depends(get_db)):
    exists = db.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    db.execute("UPDATE posts SET view_count = view_count + 1 WHERE id = ?", (post_id,))
    db.commit()
    post = _load_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    return _post_detail(post)


@router.put("/posts/{post_id}", response_model=PostDetail)
def update_post(post_id: int, payload: PostUpdate, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        "SELECT password_hash FROM posts WHERE id = ?",
        (post_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    if not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=403, detail="게시글 비밀번호가 일치하지 않습니다.")

    tags = [tag.strip().lstrip("#") for tag in payload.tags if tag.strip()][:10]
    db.execute(
        """
        UPDATE posts
        SET title = ?, body = ?, tags_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.title.strip(),
            payload.body.strip(),
            json.dumps(tags, ensure_ascii=False),
            utc_now_iso(),
            post_id,
        ),
    )
    db.commit()
    post = _load_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    return _post_detail(post)


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: int, payload: PasswordCheck, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        "SELECT password_hash FROM posts WHERE id = ?",
        (post_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    if not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=403, detail="게시글 비밀번호가 일치하지 않습니다.")

    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    return Response(status_code=204)


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=201)
def create_comment(
    post_id: int,
    payload: CommentCreate,
    db: sqlite3.Connection = Depends(get_db),
):
    if db.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    cursor = db.execute(
        """
        INSERT INTO comments (post_id, author_nickname, body, password_hash, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            post_id,
            payload.author_nickname.strip(),
            payload.body.strip(),
            hash_password(payload.password),
            utc_now_iso(),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM comments WHERE id = ?", (cursor.lastrowid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="댓글 저장 후 조회에 실패했습니다.")
    return Comment.from_row(row)


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: int,
    payload: PasswordCheck,
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute(
        "SELECT password_hash FROM comments WHERE id = ?",
        (comment_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")
    if not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=403, detail="댓글 비밀번호가 일치하지 않습니다.")

    db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    return Response(status_code=204)
