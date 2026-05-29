"""
Insert recommendation metadata into the revised Arbit schema.

Target tables:
- keywords
- event_keyword_weights
- age_restriction_keywords
- event_age_restrictions

Input:
- events_with_mood.csv
"""

from __future__ import annotations

import csv
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pymysql

from config import get_db_config


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = Path(os.getenv("EVENTS_WITH_MOOD_CSV_PATH", "/app/events_with_mood.csv"))
if not CSV_PATH.exists():
    CSV_PATH = BASE_DIR / "events_with_mood.csv"

LOG_PATH = Path(os.getenv("INSERT_ARBIT_DATA_LOG_PATH", "/app/insert_arbit_data.log"))
if not LOG_PATH.parent.exists():
    LOG_PATH = BASE_DIR / "insert_arbit_data.log"

DB_CONFIG = {
    **get_db_config(),
    "cursorclass": pymysql.cursors.DictCursor,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def clean(value: str | None, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len] if max_len else text


def split_csv_tags(value: str | None) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [tag for tag in (clean(part, 80) for part in text.split(",")) if tag]


def get_or_insert_keyword(cursor, keyword_type: str, value: str, now: datetime) -> int:
    cursor.execute(
        "SELECT id FROM keywords WHERE type = %s AND value = %s",
        (keyword_type, value),
    )
    row = cursor.fetchone()
    if row:
        return row["id"]

    cursor.execute(
        """
        INSERT INTO keywords (type, value, created_at, updated_at)
        VALUES (%s, %s, %s, %s)
        """,
        (keyword_type, value, now, now),
    )
    return cursor.lastrowid


def get_or_insert_age_keyword(cursor, value: str, now: datetime) -> int:
    cursor.execute("SELECT id FROM age_restriction_keywords WHERE value = %s", (value,))
    row = cursor.fetchone()
    if row:
        return row["id"]

    cursor.execute(
        """
        INSERT INTO age_restriction_keywords (value, created_at, updated_at)
        VALUES (%s, %s, %s)
        """,
        (value, now, now),
    )
    return cursor.lastrowid


def find_event_id(cursor, title: str, start_date: str | None) -> str | None:
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
    if row:
        return row["hex_id"]

    cursor.execute(
        "SELECT HEX(id) AS hex_id FROM events WHERE title = %s LIMIT 1",
        (title,),
    )
    row = cursor.fetchone()
    return row["hex_id"] if row else None


def upsert_event_keyword_weight(
    cursor,
    hex_event_id: str,
    keyword_id: int,
    weight: str,
    source: str,
    now: datetime,
) -> None:
    cursor.execute(
        """
        SELECT id
        FROM event_keyword_weights
        WHERE event_id = UNHEX(%s) AND keyword_id = %s
        LIMIT 1
        """,
        (hex_event_id, keyword_id),
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            """
            UPDATE event_keyword_weights
            SET weight = %s, source = %s, updated_at = %s
            WHERE id = %s
            """,
            (weight, source, now, row["id"]),
        )
        return

    cursor.execute(
        """
        INSERT INTO event_keyword_weights
            (event_id, keyword_id, weight, source, created_at, updated_at)
        VALUES
            (UNHEX(%s), %s, %s, %s, %s, %s)
        """,
        (hex_event_id, keyword_id, weight, source, now, now),
    )


def upsert_age_restriction(cursor, hex_event_id: str, age_keyword_id: int, now: datetime) -> None:
    cursor.execute(
        "SELECT id FROM event_age_restrictions WHERE event_id = UNHEX(%s) LIMIT 1",
        (hex_event_id,),
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            """
            UPDATE event_age_restrictions
            SET age_restriction_keyword_id = %s, updated_at = %s
            WHERE id = %s
            """,
            (age_keyword_id, now, row["id"]),
        )
        return

    cursor.execute(
        """
        INSERT INTO event_age_restrictions
            (event_id, age_restriction_keyword_id, created_at, updated_at)
        VALUES
            (UNHEX(%s), %s, %s, %s)
        """,
        (hex_event_id, age_keyword_id, now, now),
    )


def main() -> None:
    if not CSV_PATH.exists():
        log.error("CSV file not found: %s", CSV_PATH)
        sys.exit(1)

    stats = {"total": 0, "success": 0, "skipped_no_event": 0, "skipped_error": 0}
    now = datetime.now()

    conn = pymysql.connect(**DB_CONFIG)
    log.info("connected db=%s csv=%s", DB_CONFIG["db"], CSV_PATH)

    try:
        with open(CSV_PATH, encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for line_num, row in enumerate(reader, start=2):
                stats["total"] += 1
                title = clean(row.get("title"), 200)
                start_date = clean(row.get("start_date"))
                if not title:
                    stats["skipped_error"] += 1
                    log.warning("[SKIP] line=%s empty title", line_num)
                    continue

                try:
                    with conn.cursor() as cursor:
                        hex_event_id = find_event_id(cursor, title, start_date)
                        if not hex_event_id:
                            stats["skipped_no_event"] += 1
                            log.warning("[SKIP] line=%s event not found title=%s", line_num, title)
                            continue

                        genre = clean(row.get("genre"), 80)
                        if genre:
                            keyword_id = get_or_insert_keyword(cursor, "CATEGORY", genre, now)
                            upsert_event_keyword_weight(cursor, hex_event_id, keyword_id, "1.0000", "csv", now)

                        mood_source = clean(row.get("mood_source"), 30) or "csv"
                        mood_tags = split_csv_tags(row.get("mood_tags"))
                        mood_weight = "1.0000" if len(mood_tags) <= 1 else f"{1 / len(mood_tags):.4f}"
                        for mood in mood_tags:
                            keyword_id = get_or_insert_keyword(cursor, "MOOD", mood, now)
                            upsert_event_keyword_weight(cursor, hex_event_id, keyword_id, mood_weight, mood_source, now)

                        age_label = clean(row.get("age_label"), 50)
                        if age_label:
                            keyword_id = get_or_insert_keyword(cursor, "AGE", age_label, now)
                            upsert_event_keyword_weight(cursor, hex_event_id, keyword_id, "1.0000", "csv", now)

                            age_keyword_id = get_or_insert_age_keyword(cursor, age_label, now)
                            upsert_age_restriction(cursor, hex_event_id, age_keyword_id, now)

                    conn.commit()
                    stats["success"] += 1
                except Exception as exc:
                    conn.rollback()
                    stats["skipped_error"] += 1
                    log.error("[ERROR] line=%s title=%s error=%s", line_num, title, exc)
    finally:
        conn.close()

    log.info("done total=%s success=%s skipped_no_event=%s skipped_error=%s",
             stats["total"], stats["success"], stats["skipped_no_event"], stats["skipped_error"])


if __name__ == "__main__":
    main()
