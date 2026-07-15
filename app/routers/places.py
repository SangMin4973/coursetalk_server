from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.models import Place
from app.schemas import PlaceOut


router = APIRouter(prefix="/places", tags=["places"])


@router.get("", response_model=list[PlaceOut])
def list_places(
    region: str = Query(default="광주_전라권"),
    category: list[str] | None = Query(default=None),
    query: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
):
    conditions = ["region = ?"]
    params: list[object] = [region]

    if category:
        placeholders = ", ".join("?" for _ in category)
        conditions.append(f"category IN ({placeholders})")
        params.extend(category)

    if query.strip():
        keyword = f"%{query.strip()}%"
        conditions.append("(title LIKE ? OR address LIKE ?)")
        params.extend([keyword, keyword])

    params.append(limit)
    rows = db.execute(
        f"""
        SELECT *
        FROM places
        WHERE {' AND '.join(conditions)}
        ORDER BY title
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [Place.from_row(row) for row in rows]


@router.get("/meta")
def place_meta(db: sqlite3.Connection = Depends(get_db)):
    regions = [row["region"] for row in db.execute(
        "SELECT DISTINCT region FROM places ORDER BY region"
    ).fetchall()]
    categories = [row["category"] for row in db.execute(
        "SELECT DISTINCT category FROM places ORDER BY category"
    ).fetchall()]
    count = int(db.execute("SELECT COUNT(*) AS count FROM places").fetchone()["count"])
    return {"regions": regions, "categories": categories, "count": count}


@router.get("/{place_id}", response_model=PlaceOut)
def get_place(place_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="장소를 찾을 수 없습니다.")
    return Place.from_row(row)
