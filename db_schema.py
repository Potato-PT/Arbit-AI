from __future__ import annotations

import pymysql

from config import get_db_config, is_local_db_profile


def ensure_local_database_schema() -> None:
    if not is_local_db_profile():
        return

    config = get_db_config()
    database = config["db"]

    server_config = {key: value for key, value in config.items() if key != "db"}
    with pymysql.connect(**server_config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()

    table_config = {
        **config,
        "cursorclass": pymysql.cursors.DictCursor,
    }
    with pymysql.connect(**table_config) as conn:
        with conn.cursor() as cursor:
            for statement in LOCAL_SCHEMA_STATEMENTS:
                cursor.execute(statement)
        conn.commit()


LOCAL_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS categories (
        id BIGINT NOT NULL AUTO_INCREMENT,
        name VARCHAR(50) NOT NULL,
        created_at DATETIME(6) NULL,
        updated_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_categories_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id BINARY(16) NOT NULL,
        category_id BIGINT NOT NULL,
        title VARCHAR(200) NOT NULL,
        description TEXT NULL,
        poster_image_url VARCHAR(1000) NULL,
        venue VARCHAR(100) NOT NULL,
        venue_address VARCHAR(255) NULL,
        district VARCHAR(50) NOT NULL,
        latitude DOUBLE NULL,
        longitude DOUBLE NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        free BIT(1) NOT NULL,
        status VARCHAR(20) NOT NULL,
        average_rating DECIMAL(3,2) NOT NULL DEFAULT 0.00,
        price VARCHAR(255) NULL,
        booking_url VARCHAR(1000) NULL,
        created_at DATETIME(6) NULL,
        updated_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        KEY idx_events_category_id (category_id),
        KEY idx_events_title_start_date (title, start_date),
        CONSTRAINT fk_events_category
            FOREIGN KEY (category_id) REFERENCES categories (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS keywords (
        id BIGINT NOT NULL AUTO_INCREMENT,
        type VARCHAR(30) NOT NULL,
        value VARCHAR(80) NOT NULL,
        created_at DATETIME(6) NULL,
        updated_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_keyword_type_value (type, value)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS event_keyword_weights (
        id BIGINT NOT NULL AUTO_INCREMENT,
        event_id BINARY(16) NOT NULL,
        keyword_id BIGINT NOT NULL,
        weight DECIMAL(5,4) NOT NULL,
        source VARCHAR(30) NOT NULL,
        created_at DATETIME(6) NULL,
        updated_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_event_keyword_weight (event_id, keyword_id),
        KEY idx_event_keyword_weights_keyword_id (keyword_id),
        CONSTRAINT fk_event_keyword_weights_event
            FOREIGN KEY (event_id) REFERENCES events (id),
        CONSTRAINT fk_event_keyword_weights_keyword
            FOREIGN KEY (keyword_id) REFERENCES keywords (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS age_restriction_keywords (
        id BIGINT NOT NULL AUTO_INCREMENT,
        value VARCHAR(50) NOT NULL,
        created_at DATETIME(6) NULL,
        updated_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_age_restriction_keywords_value (value)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS event_age_restrictions (
        id BIGINT NOT NULL AUTO_INCREMENT,
        event_id BINARY(16) NOT NULL,
        age_restriction_keyword_id BIGINT NOT NULL,
        created_at DATETIME(6) NULL,
        updated_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_event_age_restriction_event (event_id),
        KEY idx_event_age_restrictions_keyword_id (age_restriction_keyword_id),
        CONSTRAINT fk_event_age_restrictions_event
            FOREIGN KEY (event_id) REFERENCES events (id),
        CONSTRAINT fk_event_age_restrictions_keyword
            FOREIGN KEY (age_restriction_keyword_id) REFERENCES age_restriction_keywords (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]
