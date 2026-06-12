"""
events 테이블에 신뢰도 ENUM 컬럼을 추가하고,
events_with_mood.csv 의 소분류_근거를 기반으로 값을 채운다.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pymysql

from config import get_db_config

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = Path(os.getenv("EVENTS_WITH_MOOD_CSV_PATH", "/app/events_with_mood.csv"))
if not CSV_PATH.exists():
    CSV_PATH = BASE_DIR / "events_with_mood.csv"

RELIABILITY_MAP = {
    "KOPIS 직접 매핑": "BEST",
    "규칙+분류기 일치": "HIGH",
    "분류기+임베딩 일치": "HIGH",
    "분류기 선택": "MID",
    "분류기 기본값": "LOW",
}

DB_CONFIG = {
    **get_db_config(),
    "cursorclass": pymysql.cursors.DictCursor,
}


def clean(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def parse_date(value: Any) -> date | None:
    if pd.isna(value):
        return None
    try:
        return pd.to_datetime(str(value)).date()
    except Exception:
        return None


def column_exists(cursor, database: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'events' AND COLUMN_NAME = '신뢰도'
        """,
        (database,),
    )
    return cursor.fetchone()["cnt"] > 0


def find_event_id(cursor, title: str, start_date: date) -> bytes | None:
    cursor.execute(
        "SELECT id FROM events WHERE title = %s AND start_date = %s LIMIT 1",
        (title, start_date),
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    config = get_db_config()
    stats = {"total": 0, "updated": 0, "skipped": 0}

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            if column_exists(cursor, config["db"]):
                print("컬럼 `신뢰도` 이미 존재 — DDL 스킵")
            else:
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN `신뢰도` ENUM('BEST','HIGH','MID','LOW') NULL"
                )
                print("컬럼 `신뢰도` 추가 완료")
            conn.commit()

        with conn.cursor() as cursor:
            for idx, row in df.iterrows():
                stats["total"] += 1

                source = clean(row.get("소분류_근거"))
                reliability = RELIABILITY_MAP.get(source) if source else None
                if reliability is None:
                    stats["skipped"] += 1
                    print(f"[SKIP] row={idx + 2} 소분류_근거={source!r} — 매핑 없음")
                    continue

                title = clean(row.get("제목"))
                start_date = parse_date(row.get("시작일"))
                if not title or start_date is None:
                    stats["skipped"] += 1
                    print(f"[SKIP] row={idx + 2} — 제목 또는 시작일 없음")
                    continue

                event_id = find_event_id(cursor, title, start_date)
                if event_id is None:
                    stats["skipped"] += 1
                    print(f"[SKIP] row={idx + 2} title={title!r} — DB에서 찾지 못함")
                    continue

                cursor.execute(
                    "UPDATE events SET `신뢰도` = %s WHERE id = %s",
                    (reliability, event_id),
                )
                stats["updated"] += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        f"\n완료  total={stats['total']}  updated={stats['updated']}  skipped={stats['skipped']}"
    )


if __name__ == "__main__":
    main()
