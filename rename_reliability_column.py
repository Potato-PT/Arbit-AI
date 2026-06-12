"""
events 테이블에서 빈 reliability 컬럼을 DROP하고
기존 신뢰도 컬럼을 reliability로 RENAME한다.
"""

from __future__ import annotations

import pymysql

from config import get_db_config

DB_CONFIG = {
    **get_db_config(),
    "cursorclass": pymysql.cursors.DictCursor,
}


def main() -> None:
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                ALTER TABLE events
                    DROP COLUMN reliability,
                    CHANGE `신뢰도` reliability ENUM('BEST','HIGH','MID','LOW') NULL
                """
            )
        conn.commit()
        print("완료: 신뢰도 → reliability 변경, 기존 reliability 컬럼 삭제")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
