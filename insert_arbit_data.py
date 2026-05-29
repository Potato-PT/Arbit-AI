"""
Arbit 프로젝트 DB 데이터 삽입 스크립트
대상 테이블: categories, classification_keywords, age_restriction_keywords,
            event_classifications, event_age_restrictions
입력 파일:  events_with_mood.csv
"""

import csv
import logging
import sys
from datetime import datetime
import uuid
import pandas as pd
import pymysql
import os

# ──────────────────────────────────────────────
# DB 접속 정보 (환경에 맞게 수정)
# ──────────────────────────────────────────────
DB_CONFIG = {
    "host": "10.54.0.3",   # Cloud SQL Auth Proxy 사용 시 그대로
    "port": 3306,
    "user": "root",
    "password": "rootroot",
    "db": "arbit-mysql",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

CSV_PATH = "/app/events_with_mood.csv"
LOG_PATH   = "/app/insert_arbit_data.log"
NOW        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ──────────────────────────────────────────────
# 로거 설정 (콘솔 + 파일 동시 출력)
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 헬퍼: INSERT IGNORE 후 id 반환
# ──────────────────────────────────────────────
def get_or_insert(cursor, table: str, col: str, value: str) -> int:
    """
    value가 이미 존재하면 기존 id를 반환하고,
    없으면 INSERT 후 새 id를 반환한다.
    """
    # 먼저 조회
    cursor.execute(
        f"SELECT id FROM `{table}` WHERE `{col}` = %s",
        (value,)
    )
    row = cursor.fetchone()
    if row:
        return row["id"]

    # 없으면 삽입
    cursor.execute(
        f"INSERT INTO `{table}` (`{col}`, created_at) VALUES (%s, %s)",
        (value, NOW)
    )
    return cursor.lastrowid


# ──────────────────────────────────────────────
# 작업 1 – categories 마스터 보완
# ──────────────────────────────────────────────
def upsert_category(cursor, genre: str) -> int:
    return get_or_insert(cursor, "categories", "name", genre)


# ──────────────────────────────────────────────
# 작업 2 – title로 event_id(BINARY 16) 조회
# ──────────────────────────────────────────────
def find_event_id(cursor, title: str):
    """
    exact match. 찾지 못하면 None 반환.
    BINARY(16) 컬럼은 SELECT 시 HEX()로 읽어 Python에서 bytes로 저장.
    INSERT 시에는 UNHEX(%s) 로 다시 넣는다.
    """
    cursor.execute(
        "SELECT HEX(id) AS hex_id FROM events WHERE title = %s LIMIT 1",
        (title,)
    )
    row = cursor.fetchone()
    if row:
        return row["hex_id"]   # e.g. "550E8400E29B41D4A716446655440000"
    return None


# ──────────────────────────────────────────────
# 작업 3 – mood_tags → classification_keywords + event_classifications
# ──────────────────────────────────────────────
def insert_classifications(cursor, hex_event_id: str, mood_tags: str) -> None:
    tags = [t.strip() for t in mood_tags.split(",") if t.strip()]
    if not tags:
        log.warning("  mood_tags 비어 있음, event_id=%s", hex_event_id)
        return

    for tag in tags:
        kw_id = get_or_insert(cursor, "classification_keywords", "value", tag)

        # uk_event_classification (event_id, classification_keyword_id) 중복 skip
        cursor.execute(
            """
            SELECT id FROM event_classifications
            WHERE event_id = UNHEX(%s) AND classification_keyword_id = %s
            LIMIT 1
            """,
            (hex_event_id, kw_id)
        )
        if cursor.fetchone():
            log.info("  [SKIP] event_classifications 중복: event=%s tag=%s", hex_event_id, tag)
            continue

        cursor.execute(
            """
            INSERT INTO event_classifications
                (event_id, classification_keyword_id, created_at)
            VALUES (UNHEX(%s), %s, %s)
            """,
            (hex_event_id, kw_id, NOW)
        )


# ──────────────────────────────────────────────
# 작업 4 – age_label → age_restriction_keywords + event_age_restrictions
# ──────────────────────────────────────────────
def insert_age_restriction(cursor, hex_event_id: str, age_label: str) -> None:
    if not age_label or not age_label.strip():
        log.warning("  age_label 비어 있음, event_id=%s", hex_event_id)
        return

    age_label = age_label.strip()
    kw_id = get_or_insert(cursor, "age_restriction_keywords", "value", age_label)

    # uk_event_age_restriction_event: event_id 단독 UNIQUE → 이미 있으면 skip
    cursor.execute(
        "SELECT id FROM event_age_restrictions WHERE event_id = UNHEX(%s) LIMIT 1",
        (hex_event_id,)
    )
    if cursor.fetchone():
        log.info("  [SKIP] event_age_restrictions 중복: event=%s", hex_event_id)
        return

    cursor.execute(
        """
        INSERT INTO event_age_restrictions
            (event_id, age_restriction_keyword_id, created_at)
        VALUES (UNHEX(%s), %s, %s)
        """,
        (hex_event_id, kw_id, NOW)
    )


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main() -> None:
    if not os.path.exists(CSV_PATH):
        log.error("CSV 파일을 찾을 수 없습니다: %s", CSV_PATH)
        sys.exit(1)
    stats = {
        "total":              0,
        "skipped_no_match":   0,
        "skipped_error":      0,
        "inserted":           0,
    }

    conn = pymysql.connect(**DB_CONFIG)
    log.info("DB 연결 성공: %s/%s", DB_CONFIG["host"], DB_CONFIG["db"])

    try:
        with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            for line_num, row in enumerate(reader, start=2):   # 헤더=1행
                stats["total"] += 1
                title     = (row.get("title")     or "").strip()
                genre     = (row.get("genre")     or "").strip()
                mood_tags = (row.get("mood_tags") or "").strip()
                age_label = (row.get("age_label") or "").strip()

                log.info("처리 중 [line %d] title=%s", line_num, title)

                # ── 작업 2: title → event_id 조회 ──────────────────
                try:
                    with conn.cursor() as cur:
                        hex_id = find_event_id(cur, title)
                except Exception as e:
                    log.error("  [ERROR] event 조회 실패 (line %d): %s", line_num, e)
                    stats["skipped_error"] += 1
                    conn.rollback()
                    continue

                if hex_id is None:
                    log.warning("  [SKIP] events 테이블에 title 없음: %s", title)
                    stats["skipped_no_match"] += 1
                    continue

                # ── 작업 1, 3, 4: 트랜잭션으로 묶어 처리 ──────────
                try:
                    with conn.cursor() as cur:

                        # 작업 1 – category
                        if genre:
                            upsert_category(cur, genre)

                        # 작업 3 – mood_tags
                        if mood_tags:
                            insert_classifications(cur, hex_id, mood_tags)

                        # 작업 4 – age_label
                        if age_label:
                            insert_age_restriction(cur, hex_id, age_label)

                    conn.commit()
                    stats["inserted"] += 1
                    log.info("  [OK] 커밋 완료: event_id=%s", hex_id)

                except Exception as e:
                    conn.rollback()
                    log.error(
                        "  [ERROR] 롤백 (line %d, title=%s): %s",
                        line_num, title, e
                    )
                    stats["skipped_error"] += 1

    finally:
        conn.close()
        log.info("DB 연결 종료")

    # ── 최종 요약 ──────────────────────────────────────────
    log.info("=" * 50)
    log.info("처리 완료 요약")
    log.info("  전체 행:           %d", stats["total"])
    log.info("  성공(커밋):        %d", stats["inserted"])
    log.info("  SKIP(title 불일치): %d", stats["skipped_no_match"])
    log.info("  SKIP(에러/롤백):   %d", stats["skipped_error"])
    log.info("  로그 파일:         %s", LOG_PATH.resolve())
    log.info("=" * 50)


if __name__ == "__main__":
    main()
