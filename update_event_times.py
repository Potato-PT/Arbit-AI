"""
Update events.time from the '행사시간' column in seoul_cultural_events.csv.

Events are matched by the same key used by insert_events.py:
- 공연/행사명 -> events.title
- 시작일      -> events.start_date
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import date, datetime
from pathlib import Path

import pymysql

from config import get_db_config


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = Path(os.getenv("EVENTS_CSV_PATH", BASE_DIR / "seoul_cultural_events.csv"))

DB_CONFIG = {
    **get_db_config(),
    "cursorclass": pymysql.cursors.DictCursor,
}


def clean(value: str | None, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text[:max_len] if max_len else text


def parse_date(value: str | None) -> date | None:
    text = clean(value)
    if not text:
        return None

    # CSV values normally look like "2026-10-15 00:00:00.0".
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def verify_time_column(cursor) -> None:
    cursor.execute(
        """
        SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'events'
          AND COLUMN_NAME = 'time'
        """,
        (DB_CONFIG["db"],),
    )
    if not cursor.fetchone():
        raise RuntimeError(
            "events.time column does not exist. Add it first, for example: "
            "ALTER TABLE events ADD COLUMN `time` VARCHAR(255) NULL;"
        )


def find_event_ids(cursor, title: str, start_date: date) -> list[bytes]:
    cursor.execute(
        """
        SELECT id
        FROM events
        WHERE title = %s AND start_date = %s
        """,
        (title, start_date),
    )
    return [row["id"] for row in cursor.fetchall()]


def update_event_time(cursor, event_id: bytes, event_time: str | None) -> None:
    cursor.execute(
        """
        UPDATE events
        SET `time` = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (event_time, datetime.now(), event_id),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update events.time from Seoul cultural event CSV")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="input CSV path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check matches without committing database changes",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.csv.exists():
        raise FileNotFoundError(f"CSV file not found: {args.csv}")

    stats = {
        "total": 0,
        "updated": 0,
        "skipped_invalid": 0,
        "skipped_not_found": 0,
        "skipped_ambiguous": 0,
    }

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            verify_time_column(cursor)

            with args.csv.open(encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                required_columns = {"공연/행사명", "시작일", "행사시간"}
                missing_columns = required_columns.difference(reader.fieldnames or [])
                if missing_columns:
                    raise ValueError(f"CSV columns missing: {sorted(missing_columns)}")

                for line_num, row in enumerate(reader, start=2):
                    stats["total"] += 1
                    title = clean(row.get("공연/행사명"), 200)
                    start_date = parse_date(row.get("시작일"))
                    event_time = clean(row.get("행사시간"), 255)

                    if not title or start_date is None:
                        stats["skipped_invalid"] += 1
                        print(f"[SKIP invalid] line={line_num} title={title}")
                        continue

                    event_ids = find_event_ids(cursor, title, start_date)
                    if not event_ids:
                        stats["skipped_not_found"] += 1
                        print(f"[SKIP not found] line={line_num} title={title} start_date={start_date}")
                        continue
                    if len(event_ids) > 1:
                        stats["skipped_ambiguous"] += 1
                        print(
                            f"[SKIP ambiguous] line={line_num} matches={len(event_ids)} "
                            f"title={title} start_date={start_date}"
                        )
                        continue

                    update_event_time(cursor, event_ids[0], event_time)
                    stats["updated"] += 1

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    mode = "dry-run" if args.dry_run else "committed"
    print(f"done mode={mode} " + " ".join(f"{key}={value}" for key, value in stats.items()))


if __name__ == "__main__":
    main()
