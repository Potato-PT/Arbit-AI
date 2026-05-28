"""
Arbit - seoul_cultural_events.csv → Cloud SQL (events + categories) 삽입 스크립트

[사전 준비]
1. Cloud SQL Auth Proxy 실행:
   ./cloud-sql-proxy --port 3306 <PROJECT_ID>:<REGION>:<INSTANCE_NAME>

2. 패키지 설치:
   pip install pandas pymysql

3. 아래 DB_CONFIG 값을 실제 환경에 맞게 수정
"""

import uuid
import pandas as pd
import pymysql
from datetime import date, datetime

# ─────────────────────────────────────────
# DB 연결 설정 (실제 값으로 교체)
# ─────────────────────────────────────────
DB_CONFIG = {
    "host": "10.54.0.3",   # Cloud SQL Auth Proxy 사용 시 그대로
    "port": 3306,
    "user": "root",
    "password": "rootroot",
    "db": "arbit-mysql",
    "charset": "utf8mb4",
}

CSV_PATH = "/app/seoul_cultural_events.csv"


# ─────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────
def parse_date(value) -> date | None:
    """'2026-10-15 00:00:00.0' 형태의 날짜 문자열을 date로 변환"""
    if pd.isna(value):
        return None
    try:
        return pd.to_datetime(str(value)).date()
    except Exception:
        return None


def calc_status(start: date | None, end: date | None) -> str:
    """날짜 비교로 UPCOMING / ONGOING / CLOSED 결정"""
    today = date.today()
    if start is None or end is None:
        return "UPCOMING"
    if today < start:
        return "UPCOMING"
    elif today > end:
        return "CLOSED"
    else:
        return "ONGOING"


def to_free(value: str) -> int:
    """'무료' → 1, '유료' → 0, 그 외 → 0"""
    return 1 if str(value).strip() == "무료" else 0


def make_uuid_bytes() -> bytes:
    """UUID를 BINARY(16) 형태의 bytes로 변환"""
    return uuid.uuid4().bytes


def get_or_create_category(cursor, name: str, category_cache: dict) -> int:
    """categories 테이블에서 id 조회, 없으면 INSERT 후 id 반환"""
    if name in category_cache:
        return category_cache[name]

    cursor.execute("SELECT id FROM categories WHERE name = %s", (name,))
    row = cursor.fetchone()
    if row:
        category_cache[name] = row[0]
        return row[0]

    now = datetime.now()
    cursor.execute(
        "INSERT INTO categories (name, created_at) VALUES (%s, %s)",
        (name, now),
    )
    category_cache[name] = cursor.lastrowid
    print(f"  [categories] INSERT: '{name}' → id={cursor.lastrowid}")
    return cursor.lastrowid


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────
def main():
    df = pd.read_csv(CSV_PATH)
    print(f"CSV 로드 완료: {len(df)}행")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    print("DB 연결 성공")

    category_cache: dict[str, int] = {}
    now = datetime.now()

    insert_sql = """
        INSERT INTO events (
            id, category_id, title, description,
            venue, district,
            start_date, end_date,
            free, status,
            average_rating, created_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            0.00, %s
        )
    """

    success = 0
    skipped = 0

    for idx, row in df.iterrows():
        try:
            # category_id 처리
            category_name = str(row["분류"]).strip()
            category_id = get_or_create_category(cursor, category_name, category_cache)

            # description: 크롤링 값 우선, 없으면 원본
            description = row.get("프로그램소개_크롤링")
            if pd.isna(description):
                description = row.get("프로그램소개")
            if pd.isna(description):
                description = None
            # events.description은 VARCHAR(1000) → 초과 시 자름
            if description:
                description = str(description)[:1000]

            start_date = parse_date(row["시작일"])
            end_date = parse_date(row["종료일"])
            status = calc_status(start_date, end_date)

            cursor.execute(insert_sql, (
                make_uuid_bytes(),
                category_id,
                str(row["공연/행사명"])[:200],   # VARCHAR(200)
                description,
                str(row["장소"])[:100],          # VARCHAR(100)
                str(row["자치구"])[:50],          # VARCHAR(50)
                start_date,
                end_date,
                to_free(row["유무료"]),
                status,
                now,
            ))
            success += 1

        except Exception as e:
            print(f"  [SKIP] row {idx} - {row.get('공연/행사명', '?')} | 오류: {e}")
            skipped += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n완료: 성공 {success}건 / 스킵 {skipped}건")
    print(f"categories 신규 등록: {list(category_cache.keys())}")


if __name__ == "__main__":
    main()
