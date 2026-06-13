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
        `time` VARCHAR(255) NULL,
        free BIT(1) NOT NULL,
        status VARCHAR(20) NOT NULL,
        reliability ENUM('BEST','HIGH','MID','LOW') NULL,
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
    """
    CREATE TABLE IF NOT EXISTS users (
        id BINARY(16) NOT NULL,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        age INT NOT NULL,
        gender ENUM('FEMALE','MALE','NONSELECT') NULL,
        nickname VARCHAR(100) NOT NULL,
        password VARCHAR(255) NOT NULL,
        profile_image_url VARCHAR(1000) NULL,
        residential_area VARCHAR(255) NOT NULL,
        residential_latitude DOUBLE NULL,
        residential_longitude DOUBLE NULL,
        username VARCHAR(50) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY UKr43af9ap4edm43mmtq01oddj6 (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS preference_keywords (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        value VARCHAR(50) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY UKrlhr8nor2lysysnp3c1henj6k (value)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS classification_keywords (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        value VARCHAR(50) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY UKi44srkkgs99u8ah2449aw61fp (value)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS bookmarks (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        event_id BINARY(16) NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_bookmark_user_event (user_id, event_id),
        KEY FK5180rcunaogkv8wgj4egf55xd (event_id),
        CONSTRAINT FK5180rcunaogkv8wgj4egf55xd
            FOREIGN KEY (event_id) REFERENCES events (id),
        CONSTRAINT FKdbsho2e05w5r13fkjqfjmge5f
            FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS event_action_logs (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        action_type ENUM('DETAIL_VIEW','HOMEPAGE_CLICK') NOT NULL,
        source ENUM('EVENT_DETAIL','HOME','RECOMMENDATION','SEARCH') NULL,
        event_id BINARY(16) NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        KEY idx_event_action_user_created (user_id, created_at),
        KEY idx_event_action_event_type_created (event_id, action_type, created_at),
        KEY idx_event_action_user_event_type (user_id, event_id, action_type),
        CONSTRAINT FK5xj8gdhvs6f22w4df9gjk9stl
            FOREIGN KEY (user_id) REFERENCES users (id),
        CONSTRAINT FKr3iybip6hi8oh8e5989yhlks5
            FOREIGN KEY (event_id) REFERENCES events (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS event_classifications (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        classification_keyword_id BIGINT NOT NULL,
        event_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_event_classification (event_id, classification_keyword_id),
        KEY FKqs9rp95q0l6m30ce8kedwtebi (classification_keyword_id),
        CONSTRAINT FKdg00xh99f7lrtkwukrpbff7qb
            FOREIGN KEY (event_id) REFERENCES events (id),
        CONSTRAINT FKqs9rp95q0l6m30ce8kedwtebi
            FOREIGN KEY (classification_keyword_id) REFERENCES classification_keywords (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS event_detail_view_logs (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        event_id BINARY(16) NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        KEY FKcv9s5corewef07bjmd100qux3 (event_id),
        KEY FKmwfca2dt8p5n75nu0dcua2toi (user_id),
        CONSTRAINT FKcv9s5corewef07bjmd100qux3
            FOREIGN KEY (event_id) REFERENCES events (id),
        CONSTRAINT FKmwfca2dt8p5n75nu0dcua2toi
            FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS event_keywords (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        event_id BINARY(16) NOT NULL,
        preference_keyword_id BIGINT NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_event_keyword (event_id, preference_keyword_id),
        KEY FKerkmcq0jc771sk7a0ovcsu63q (preference_keyword_id),
        CONSTRAINT FKerkmcq0jc771sk7a0ovcsu63q
            FOREIGN KEY (preference_keyword_id) REFERENCES preference_keywords (id),
        CONSTRAINT FKhd0upbna915hj6f3qsausjhik
            FOREIGN KEY (event_id) REFERENCES events (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendation_runs (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        algorithm VARCHAR(50) NOT NULL,
        input_event_ids_json TEXT NULL,
        model_version VARCHAR(50) NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        KEY FKlw8gk33nassjenqe86naypwj (user_id),
        CONSTRAINT FKlw8gk33nassjenqe86naypwj
            FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendation_items (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        feature_scores_json TEXT NULL,
        rank_no INT NOT NULL,
        reason VARCHAR(300) NOT NULL,
        score DECIMAL(8,4) NOT NULL,
        event_id BINARY(16) NOT NULL,
        run_id BIGINT NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_recommendation_item_run_event (run_id, event_id),
        KEY FKfm492rvyjq1pemtf9v6cs81v5 (event_id),
        CONSTRAINT FKfm492rvyjq1pemtf9v6cs81v5
            FOREIGN KEY (event_id) REFERENCES events (id),
        CONSTRAINT FKi0hfbk90ox9nwilc10nssxdbo
            FOREIGN KEY (run_id) REFERENCES recommendation_runs (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendations (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        match_score DECIMAL(5,2) NOT NULL,
        reason VARCHAR(500) NOT NULL,
        event_id BINARY(16) NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_recommendation_user_event (user_id, event_id),
        KEY FKgmputyyanqqarbmcge1dt6lc5 (event_id),
        CONSTRAINT FK3c9w1lipqdutm65a9inevwfp0
            FOREIGN KEY (user_id) REFERENCES users (id),
        CONSTRAINT FKgmputyyanqqarbmcge1dt6lc5
            FOREIGN KEY (event_id) REFERENCES events (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        content VARCHAR(200) NOT NULL,
        rating INT NOT NULL,
        verification_image_url VARCHAR(500) NULL,
        event_id BINARY(16) NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_review_user_event (user_id, event_id),
        KEY FKem6jjo18jyueiqhferf3dwfbx (event_id),
        CONSTRAINT FKcgy7qjc1r99dp117y9en6lxye
            FOREIGN KEY (user_id) REFERENCES users (id),
        CONSTRAINT FKem6jjo18jyueiqhferf3dwfbx
            FOREIGN KEY (event_id) REFERENCES events (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_categories (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        category_id BIGINT NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_user_category (user_id, category_id),
        KEY FK6r91537otve5embvcuv40is3j (category_id),
        CONSTRAINT FK6r91537otve5embvcuv40is3j
            FOREIGN KEY (category_id) REFERENCES categories (id),
        CONSTRAINT FKdqpxght56isds8smi1frxg0xo
            FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_keyword_weights (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        source VARCHAR(30) NOT NULL,
        weight DECIMAL(5,4) NOT NULL,
        keyword_id BIGINT NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_user_keyword_weight (user_id, keyword_id),
        KEY FK8auk83768oh9os7g9p154cf0y (keyword_id),
        CONSTRAINT FK8auk83768oh9os7g9p154cf0y
            FOREIGN KEY (keyword_id) REFERENCES keywords (id),
        CONSTRAINT FKcn1cwx8hxvitxcnhtfh90ptid
            FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preference_events (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        event_id BINARY(16) NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_user_preference_event (user_id, event_id),
        CONSTRAINT FKi7reblrs8gboavc6xh1kn1154
            FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preference_keywords (
        id BIGINT NOT NULL AUTO_INCREMENT,
        created_at DATETIME(6) NOT NULL,
        updated_at DATETIME(6) NULL,
        preference_keyword_id BIGINT NOT NULL,
        user_id BINARY(16) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uk_user_preference_keyword (user_id, preference_keyword_id),
        KEY FKem76rmm4i1yydq4ww3qak3b49 (preference_keyword_id),
        CONSTRAINT FKem76rmm4i1yydq4ww3qak3b49
            FOREIGN KEY (preference_keyword_id) REFERENCES preference_keywords (id),
        CONSTRAINT FKkkfhgwxp8ddrsrq6usa9s73y4
            FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]
