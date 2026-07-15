from __future__ import annotations

import hashlib
import math
import sqlite3
from datetime import datetime, timedelta


from app.core.config import Settings
from app.models import Place
from app.schemas import (
    AIPlanSelection,
    AISelectedStop,
    ItineraryRequest,
    ItineraryResponse,
    ItineraryStop,
    PlaceOut,
    ShareDraft,
)


PREFERENCE_TO_CATEGORY = {
    "맛집": "음식점",
    "음식": "음식점",
    "식당": "음식점",
    "카페": "음식점",
    "전시회": "문화시설",
    "전시": "문화시설",
    "미술관": "문화시설",
    "박물관": "문화시설",
    "문화": "문화시설",
    "관광": "관광지",
    "관광명소": "관광지",
    "명소": "관광지",
    "쇼핑": "쇼핑",
    "체험": "레포츠",
    "레포츠": "레포츠",
    "액티비티": "레포츠",
    "축제": "축제공연행사",
    "숙박": "숙박",
}

FALLBACK_CATEGORIES = ["문화시설", "관광지", "쇼핑", "축제공연행사", "레포츠"]


def parse_clock(value: str) -> datetime:
    return datetime.strptime(value, "%H:%M")


def haversine_km(a: Place, b: Place) -> float:
    radius = 6371.0
    lat1 = math.radians(a.latitude)
    lat2 = math.radians(b.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def estimate_travel_minutes(a: Place | None, b: Place) -> int:
    if a is None:
        return 0
    distance = haversine_km(a, b)
    return max(10, min(45, round(10 + distance * 4)))


def normalize_categories(preferences: list[str]) -> list[str]:
    categories: list[str] = []
    for preference in preferences:
        mapped = PREFERENCE_TO_CATEGORY.get(preference, preference)
        if mapped not in categories:
            categories.append(mapped)
    return categories


def _candidate_places(
    db: sqlite3.Connection,
    region: str,
    desired_categories: list[str],
    seed_text: str,
    per_category: int = 12,
) -> tuple[list[Place], list[str]]:
    warnings: list[str] = []
    candidates: list[Place] = []

    for category in desired_categories:
        db_rows = db.execute(
            """
            SELECT * FROM places
            WHERE region = ? AND category = ?
            ORDER BY title
            LIMIT 80
            """,
            (region, category),
        ).fetchall()
        rows = [Place.from_row(row) for row in db_rows]
        if not rows:
            warnings.append(f"{region} 제공 데이터에 '{category}' 항목이 없어 다른 유형으로 보완했습니다.")
            continue

        digest = hashlib.sha256(f"{seed_text}:{category}".encode("utf-8")).digest()
        offset = int.from_bytes(digest[:4], "big") % len(rows)
        rotated = rows[offset:] + rows[:offset]
        candidates.extend(rotated[:per_category])

    # 요청 유형이 일부 비어 있더라도 일정이 한 종류 장소로만 채워지지 않도록
    # 보완 카테고리 후보를 항상 함께 준비한다.
    placeholders = ", ".join("?" for _ in FALLBACK_CATEGORIES)
    fallback_db_rows = db.execute(
        f"""
        SELECT * FROM places
        WHERE region = ? AND category IN ({placeholders})
        ORDER BY title
        LIMIT 180
        """,
        (region, *FALLBACK_CATEGORIES),
    ).fetchall()
    fallback_rows = [Place.from_row(row) for row in fallback_db_rows]
    known = {place.id for place in candidates}
    candidates.extend(place for place in fallback_rows if place.id not in known)

    return candidates[:60], warnings


def _rule_based_selection(candidates: list[Place], stop_count: int, categories: list[str]) -> AIPlanSelection:
    if len(candidates) < 2:
        raise ValueError("일정을 만들 수 있는 장소 데이터가 부족합니다.")

    selected: list[Place] = []
    # 먼저 사용자가 요청한 유형을 하나씩 반영한다.
    for category in categories:
        match = next((place for place in candidates if place.category == category and place not in selected), None)
        if match:
            selected.append(match)
        if len(selected) >= stop_count:
            break

    # 요청 유형의 데이터가 부족할 때는 같은 유형만 반복하지 않고 다른 유형으로 보완한다.
    for category in FALLBACK_CATEGORIES:
        if category in {place.category for place in selected}:
            continue
        match = next((place for place in candidates if place.category == category and place not in selected), None)
        if match:
            selected.append(match)
        if len(selected) >= stop_count:
            break

    for place in candidates:
        if place not in selected:
            selected.append(place)
        if len(selected) >= stop_count:
            break

    # 첫 장소 이후에는 가장 가까운 장소를 이어 붙여 과도한 이동을 줄인다.
    ordered = [selected.pop(0)]
    while selected:
        previous = ordered[-1]
        nearest = min(selected, key=lambda place: haversine_km(previous, place))
        ordered.append(nearest)
        selected.remove(nearest)

    stops = [
        AISelectedStop(
            place_id=place.id,
            duration_minutes=60,
            reason=f"{place.category} 선호와 이동 동선을 함께 고려한 실제 공공데이터 장소입니다.",
        )
        for place in ordered
    ]
    return AIPlanSelection(
        title="조건에 맞춘 광주 반나절 코스",
        summary="선호 유형을 우선 반영하고 장소 간 직선거리가 지나치게 멀지 않도록 구성했습니다.",
        stops=stops,
    )


def _openai_selection(
    settings: Settings,
    request: ItineraryRequest,
    candidates: list[Place],
    stop_count: int,
) -> AIPlanSelection:
    candidate_text = "\n".join(
        f"- id={place.id} | {place.title} | {place.category} | {place.address} | 위도={place.latitude}, 경도={place.longitude}"
        for place in candidates
    )
    instructions = (
        "당신은 여행 일정 설계 도우미입니다. 반드시 제공된 후보의 place_id만 선택하세요. "
        "존재하지 않는 장소를 만들거나 후보 밖의 장소를 언급하면 안 됩니다. "
        "일정은 사용 시간 안에 들어가야 하고, 장소 수는 요청한 개수와 같아야 합니다. "
        "같은 place_id를 중복 선택하지 마세요. 가능한 한 서로 다른 카테고리를 섞고, 이동 부담이 너무 크지 않도록 가까운 장소를 조합하세요."
    )
    user_input = f"""
지역: {request.region}
시간: {request.start_time}~{request.end_time}
동행: {request.companion}
선호: {', '.join(request.preferences)}
추가 요청: {request.extra_request or '없음'}
선택할 장소 수: {stop_count}

후보 장소:
{candidate_text}
""".strip()

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.parse(
        model=settings.openai_model,
        instructions=instructions,
        input=user_input,
        text_format=AIPlanSelection,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("OpenAI가 구조화된 일정을 반환하지 않았습니다.")
    return parsed


def _validate_selection(selection: AIPlanSelection, candidates: list[Place], stop_count: int) -> list[tuple[Place, AISelectedStop]]:
    by_id = {place.id: place for place in candidates}
    seen: set[int] = set()
    validated: list[tuple[Place, AISelectedStop]] = []
    for selected in selection.stops:
        place = by_id.get(selected.place_id)
        if place is None or place.id in seen:
            continue
        seen.add(place.id)
        validated.append((place, selected))
        if len(validated) >= stop_count:
            break
    if len(validated) < 2:
        raise ValueError("유효한 장소 선택 결과가 부족합니다.")
    return validated


def _build_timed_stops(
    pairs: list[tuple[Place, AISelectedStop]],
    request: ItineraryRequest,
) -> list[ItineraryStop]:
    start = parse_clock(request.start_time)
    end = parse_clock(request.end_time)
    total_minutes = int((end - start).total_seconds() // 60)

    # 선택된 장소 수가 실제 가용 시간에 맞지 않으면 뒤에서부터 줄인다.
    while len(pairs) > 2:
        travel_total = sum(
            estimate_travel_minutes(pairs[index - 1][0] if index else None, pair[0])
            for index, pair in enumerate(pairs)
        )
        if total_minutes - travel_total >= 40 * len(pairs):
            break
        pairs.pop()

    travel_minutes = [
        estimate_travel_minutes(pairs[index - 1][0] if index else None, pair[0])
        for index, pair in enumerate(pairs)
    ]
    remaining = total_minutes - sum(travel_minutes)
    base_stay = max(35, remaining // len(pairs))

    current = start
    stops: list[ItineraryStop] = []
    for index, ((place, selected), travel) in enumerate(zip(pairs, travel_minutes, strict=True), start=1):
        current += timedelta(minutes=travel)
        remaining_slots = len(pairs) - index + 1
        remaining_until_end = int((end - current).total_seconds() // 60)
        stay = min(selected.duration_minutes, base_stay)
        stay = max(30, min(stay, remaining_until_end - 30 * (remaining_slots - 1)))
        stop_end = min(end, current + timedelta(minutes=stay))
        actual_stay = max(0, int((stop_end - current).total_seconds() // 60))

        stops.append(
            ItineraryStop(
                order=index,
                place=PlaceOut.model_validate(place),
                start_time=current.strftime("%H:%M"),
                end_time=stop_end.strftime("%H:%M"),
                stay_minutes=actual_stay,
                travel_minutes_from_previous=travel,
                reason=selected.reason,
            )
        )
        current = stop_end

    return stops


def _make_share_draft(
    request: ItineraryRequest,
    title: str,
    summary: str,
    stops: list[ItineraryStop],
) -> ShareDraft:
    schedule_lines = [
        f"{stop.start_time}~{stop.end_time}  {stop.place.title} ({stop.place.category})\n"
        f"- {stop.place.address or '주소 정보 없음'}\n- 추천 이유: {stop.reason}"
        for stop in stops
    ]
    body = (
        f"AI가 추천한 {request.region} 여행 일정입니다.\n\n"
        f"동행: {request.companion}\n"
        f"선호: {', '.join(request.preferences)}\n"
        f"요약: {summary}\n\n"
        + "\n\n".join(schedule_lines)
        + "\n\n동선이나 더 좋은 장소가 있다면 익명 댓글로 알려주세요!"
    )
    tags = [request.region, request.companion, *request.preferences, "AI여행코스"]
    return ShareDraft(title=title, body=body, tags=list(dict.fromkeys(tags))[:10])


def generate_itinerary(db: sqlite3.Connection, settings: Settings, request: ItineraryRequest) -> ItineraryResponse:
    start = parse_clock(request.start_time)
    end = parse_clock(request.end_time)
    total_minutes = int((end - start).total_seconds() // 60)
    if total_minutes < 120:
        raise ValueError("여행 시간은 최소 2시간 이상이어야 합니다.")
    if total_minutes > 720:
        raise ValueError("한 번에 생성할 수 있는 일정은 최대 12시간입니다.")

    stop_count = max(2, min(5, round(total_minutes / 75)))
    categories = normalize_categories(request.preferences)
    seed_text = f"{request.region}|{request.start_time}|{request.end_time}|{request.companion}|{'/'.join(request.preferences)}|{request.extra_request}"
    candidates, warnings = _candidate_places(db, request.region, categories, seed_text)
    if len(candidates) < 2:
        raise ValueError("선택한 지역에서 위치 정보가 있는 장소를 충분히 찾지 못했습니다.")

    source = "rule_based"
    selection: AIPlanSelection
    if settings.openai_api_key:
        try:
            selection = _openai_selection(settings, request, candidates, stop_count)
            source = "openai"
        except Exception as exc:  # 외부 API 장애가 전체 시연을 막지 않도록 폴백
            warnings.append(f"AI 호출에 실패해 규칙 기반 일정으로 전환했습니다: {type(exc).__name__}")
            selection = _rule_based_selection(candidates, stop_count, categories)
    else:
        warnings.append("OPENAI_API_KEY가 없어 규칙 기반 일정 생성기를 사용했습니다.")
        selection = _rule_based_selection(candidates, stop_count, categories)

    try:
        pairs = _validate_selection(selection, candidates, stop_count)
    except ValueError:
        selection = _rule_based_selection(candidates, stop_count, categories)
        pairs = _validate_selection(selection, candidates, stop_count)
        source = "rule_based"
        warnings.append("AI 선택 결과를 검증하지 못해 실제 데이터 기반 규칙 일정으로 교체했습니다.")

    stops = _build_timed_stops(pairs, request)
    share_draft = _make_share_draft(request, selection.title, selection.summary, stops)

    return ItineraryResponse(
        title=selection.title,
        summary=selection.summary,
        region=request.region,
        companion=request.companion,
        preferences=request.preferences,
        source=source,
        stops=stops,
        warnings=warnings,
        share_draft=share_draft,
    )
