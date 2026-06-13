"""
Insert Seoul cultural event rows into the revised Arbit schema.

Target tables:
- categories
- events

Input:
- seoul_cultural_events.csv
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pymysql

from config import get_db_config
from db_schema import ensure_local_database_schema


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = Path(os.getenv("EVENTS_CSV_PATH", "/app/seoul_cultural_events.csv"))
if not CSV_PATH.exists():
    CSV_PATH = BASE_DIR / "seoul_cultural_events.csv"

DB_CONFIG = {
    **get_db_config(),
    "cursorclass": pymysql.cursors.DictCursor,
}


def clean(value: Any, max_len: int | None = None) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len] if max_len else text


def parse_date(value: Any) -> date | None:
    if pd.isna(value):
        return None
    try:
        return pd.to_datetime(str(value)).date()
    except Exception:
        return None


def parse_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def calc_status(start: date | None, end: date | None) -> str:
    today = date.today()
    if start is None or end is None:
        return "UPCOMING"
    if today < start:
        return "UPCOMING"
    if today > end:
        return "CLOSED"
    return "ONGOING"


def to_free(value: Any) -> int:
    return 1 if clean(value) == "무료" else 0


def get_or_create_category(cursor, name: str, now: datetime, cache: dict[str, int]) -> int:
    if name in cache:
        return cache[name]

    cursor.execute("SELECT id FROM categories WHERE name = %s", (name,))
    row = cursor.fetchone()
    if row:
        cache[name] = row["id"]
        return row["id"]

    cursor.execute(
        "INSERT INTO categories (name, created_at, updated_at) VALUES (%s, %s, %s)",
        (name, now, now),
    )
    cache[name] = cursor.lastrowid
    return cursor.lastrowid


def find_event(cursor, title: str, start_date: date | None) -> str | None:
    cursor.execute(
        """
        SELECT HEX(id) AS hex_id
        FROM events
        WHERE title = %s AND start_date = %s
        LIMIT 1
        """,
        (title, start_date),
    )
    row = cursor.fetchone()
    return row["hex_id"] if row else None


def insert_event(cursor, row: pd.Series, category_id: int, now: datetime) -> None:
    title = clean(row.get("공연/행사명"), 200)
    if not title:
        raise ValueError("title is empty")

    start_date = parse_date(row.get("시작일"))
    end_date = parse_date(row.get("종료일"))
    if start_date is None or end_date is None:
        raise ValueError(f"invalid date: title={title}")

    description = clean(row.get("프로그램소개_크롤링")) or clean(row.get("프로그램소개"))
    venue = clean(row.get("장소"), 100) or "미정"
    district = clean(row.get("자치구"), 50) or "미정"
    poster_image_url = clean(row.get("대표이미지"), 1000)
    price = clean(row.get("이용요금"), 255)
    booking_url = clean(row.get("홈페이지주소"), 1000)

    params = {
        "category_id": category_id,
        "title": title,
        "description": description,
        "poster_image_url": poster_image_url,
        "venue": venue,
        "venue_address": None,
        "district": district,
        "latitude": parse_float(row.get("위도")),
        "longitude": parse_float(row.get("경도")),
        "start_date": start_date,
        "end_date": end_date,
        "free": to_free(row.get("유무료")),
        "status": calc_status(start_date, end_date),
        "price": price,
        "booking_url": booking_url,
        "updated_at": now,
    }

    existing_hex_id = find_event(cursor, title, start_date)
    if existing_hex_id:
        cursor.execute(
            """
            UPDATE events
            SET category_id = %(category_id)s,
                description = %(description)s,
                poster_image_url = %(poster_image_url)s,
                venue = %(venue)s,
                venue_address = %(venue_address)s,
                district = %(district)s,
                latitude = %(latitude)s,
                longitude = %(longitude)s,
                end_date = %(end_date)s,
                free = %(free)s,
                status = %(status)s,
                price = %(price)s,
                booking_url = %(booking_url)s,
                updated_at = %(updated_at)s
            WHERE id = UNHEX(%(hex_id)s)
            """,
            {**params, "hex_id": existing_hex_id},
        )
        return

    cursor.execute(
        """
        INSERT INTO events (
            id, category_id, title, description, poster_image_url,
            venue, venue_address, district, latitude, longitude,
            start_date, end_date, free, status, average_rating,
            price, booking_url, created_at, updated_at
        ) VALUES (
            %(id)s, %(category_id)s, %(title)s, %(description)s, %(poster_image_url)s,
            %(venue)s, %(venue_address)s, %(district)s, %(latitude)s, %(longitude)s,
            %(start_date)s, %(end_date)s, %(free)s, %(status)s, 0.00,
            %(price)s, %(booking_url)s, %(created_at)s, %(updated_at)s
        )
        """,
        {
            **params,
            "id": uuid.uuid4().bytes,
            "title": title,
            "created_at": now,
        },
    )


def main() -> None:
    ensure_local_database_schema()

    df = pd.read_csv(CSV_PATH)
    now = datetime.now()
    stats = {"total": 0, "success": 0, "skipped": 0}
    category_cache: dict[str, int] = {}

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            for idx, row in df.iterrows():
                stats["total"] += 1
                try:
                    category_name = clean(row.get("분류"), 50) or "기타"
                    category_id = get_or_create_category(cursor, category_name, now, category_cache)
                    insert_event(cursor, row, category_id, now)
                    stats["success"] += 1
                except Exception as exc:
                    stats["skipped"] += 1
                    print(f"[SKIP] row={idx + 2} title={row.get('공연/행사명')} error={exc}")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"done total={stats['total']} success={stats['success']} skipped={stats['skipped']}")


if __name__ == "__main__":
    main()
