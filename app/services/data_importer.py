from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from collections.abc import Iterable
from pathlib import Path


UNICODE_ESCAPE = re.compile(r"#U([0-9a-fA-F]{4})")


INSERT_PLACE_SQL = """
INSERT OR IGNORE INTO places (
    content_id, content_type_id, region, category, title,
    address, address_detail, telephone, latitude, longitude,
    image_url, thumbnail_url, source_modified_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def decode_archive_name(value: str) -> str:
    return UNICODE_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), value)


def _to_float(value: object) -> float | None:
    try:
        number = float(str(value).strip())
        return number if number != 0 else None
    except (TypeError, ValueError):
        return None


def _flush_places(db: sqlite3.Connection, rows: list[tuple[object, ...]]) -> int:
    if not rows:
        return 0
    before = db.total_changes
    db.executemany(INSERT_PLACE_SQL, rows)
    db.commit()
    changed = db.total_changes - before
    rows.clear()
    return changed


def import_places_from_zip(
    db: sqlite3.Connection,
    zip_path: Path,
    allowed_regions: Iterable[str] | None = None,
) -> int:
    if not zip_path.exists():
        raise FileNotFoundError(f"데이터 압축 파일을 찾을 수 없습니다: {zip_path}")

    regions = {region.strip() for region in (allowed_regions or []) if region.strip()}
    rows: list[tuple[object, ...]] = []
    imported = 0

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            decoded_name = decode_archive_name(member.filename)
            if not decoded_name.endswith(".json"):
                continue

            payload = json.loads(archive.read(member).decode("utf-8"))
            region = str(payload.get("region", "")).strip()
            if regions and region not in regions:
                continue

            category = str(payload.get("contentType", "")).strip()
            content_type_id = str(payload.get("contentTypeId", "")).strip()

            for item in payload.get("items", []):
                latitude = _to_float(item.get("mapy"))
                longitude = _to_float(item.get("mapx"))
                content_id = str(item.get("contentid", "")).strip()
                title = str(item.get("title", "")).strip()
                if not content_id or not title or latitude is None or longitude is None:
                    continue

                rows.append(
                    (
                        content_id,
                        content_type_id,
                        region,
                        category,
                        title,
                        str(item.get("addr1", "")).strip(),
                        str(item.get("addr2", "")).strip(),
                        str(item.get("tel", "")).strip(),
                        latitude,
                        longitude,
                        str(item.get("firstimage", "")).strip(),
                        str(item.get("firstimage2", "")).strip(),
                        str(item.get("modifiedtime", "")).strip(),
                    )
                )

                if len(rows) >= 1000:
                    imported += _flush_places(db, rows)

    imported += _flush_places(db, rows)
    return imported


def ensure_places_loaded(
    db: sqlite3.Connection,
    zip_path: Path,
    allowed_regions: list[str],
) -> int:
    count = int(db.execute("SELECT COUNT(*) AS count FROM places").fetchone()["count"])
    if count > 0:
        return 0
    return import_places_from_zip(db, zip_path, allowed_regions)
