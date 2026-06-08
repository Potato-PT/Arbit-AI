from __future__ import annotations

from collections import Counter
from datetime import date
import os
import uuid

import pandas as pd
import pymysql

from config import get_db_config


DATA_SOURCE = "mysql"
TODAY = date.today()

WEIGHTS_FOCUSED = {"genre": 0.40, "mood": 0.45, "urgency": 0.15}
WEIGHTS_DISPERSED = {"genre": 0.30, "mood": 0.55, "urgency": 0.15}
EVENT_COLUMNS = [
    "event_id",
    "title",
    "genre",
    "district",
    "is_free",
    "start_date",
    "end_date",
    "description",
    "age_label",
    "mood_tags",
    "mood_source",
    "status",
    "days_left",
]


def _empty_events_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=EVENT_COLUMNS)


def _to_bool(value) -> bool:
    if isinstance(value, (bytes, bytearray)):
        return value != b"\x00"
    return bool(value)


def _to_uuid(hex_id) -> str:
    return str(uuid.UUID(hex=str(hex_id)))


def _status(start_date: date, end_date: date, db_status: str) -> str:
    if db_status == "CLOSED" or end_date < TODAY:
        return "CLOSED"
    if start_date > TODAY:
        return "UPCOMING"
    if (end_date - TODAY).days <= 7:
        return "CLOSING_SOON"
    return "ONGOING"


def load_data() -> pd.DataFrame:
    query = """
        SELECT
            HEX(e.id) AS event_id,
            e.title,
            c.name AS genre,
            e.district,
            e.free AS is_free,
            e.start_date,
            e.end_date,
            e.description,
            e.status,
            ark.value AS age_label,
            k.type AS keyword_type,
            k.value AS keyword_value,
            ekw.source AS keyword_source
        FROM events e
        JOIN categories c ON c.id = e.category_id
        LEFT JOIN event_age_restrictions ear ON ear.event_id = e.id
        LEFT JOIN age_restriction_keywords ark ON ark.id = ear.age_restriction_keyword_id
        LEFT JOIN event_keyword_weights ekw ON ekw.event_id = e.id
        LEFT JOIN keywords k ON k.id = ekw.keyword_id
        WHERE e.status <> 'CLOSED'
        ORDER BY e.created_at DESC
    """

    if os.getenv("ARBIT_DB_PROFILE", "").lower() == "h2":
        return _load_h2_data(query)

    config = {
        **get_db_config(),
        "cursorclass": pymysql.cursors.DictCursor,
    }
    with pymysql.connect(**config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    events: dict[str, dict] = {}
    for row in rows:
        event_id = _to_uuid(row["event_id"])
        event = events.setdefault(
            event_id,
            {
                "event_id": event_id,
                "title": row["title"],
                "genre": row["genre"],
                "district": row["district"],
                "is_free": _to_bool(row["is_free"]),
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "description": row["description"],
                "age_label": row["age_label"],
                "mood_tags": [],
                "mood_source": None,
                "status": _status(row["start_date"], row["end_date"], row["status"]),
                "days_left": max(0, (row["end_date"] - TODAY).days),
            },
        )

        keyword_type = row.get("keyword_type")
        keyword_value = row.get("keyword_value")
        if keyword_type == "MOOD" and keyword_value:
            event["mood_tags"].append(keyword_value)
            event["mood_source"] = event["mood_source"] or row.get("keyword_source")
        elif keyword_type == "AGE" and keyword_value and not event["age_label"]:
            event["age_label"] = keyword_value

    for event in events.values():
        if not event["mood_tags"]:
            event["mood_tags"] = ["default"]
        if not event["mood_source"]:
            event["mood_source"] = "db"
        if not event["age_label"]:
            event["age_label"] = "all"

    df = pd.DataFrame(events.values(), columns=EVENT_COLUMNS)
    if df.empty:
        return _empty_events_frame()
    return df[df["status"] != "CLOSED"].reset_index(drop=True)


def _load_h2_data(query: str) -> pd.DataFrame:
    import jaydebeapi

    query = query.replace("HEX(e.id) AS event_id", "RAWTOHEX(e.id) AS event_id")
    for alias in (
        "event_id",
        "genre",
        "is_free",
        "age_label",
        "keyword_type",
        "keyword_value",
        "keyword_source",
    ):
        query = query.replace(f" AS {alias}", f' AS "{alias}"')
    h2_jar = os.environ["H2_JAR_PATH"]
    jdbc_url = os.getenv(
        "H2_JDBC_URL",
        "jdbc:h2:tcp://localhost:9092/mem:arbitlocal;MODE=MySQL;DATABASE_TO_LOWER=TRUE;NON_KEYWORDS=VALUE;DB_CLOSE_DELAY=-1",
    )
    conn = jaydebeapi.connect("org.h2.Driver", jdbc_url, ["sa", ""], h2_jar)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [column[0].lower() for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

    return _rows_to_frame(rows)


def _rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    events: dict[str, dict] = {}
    for row in rows:
        event_id = _to_uuid(row["event_id"])
        event = events.setdefault(
            event_id,
            {
                "event_id": event_id,
                "title": row["title"],
                "genre": row["genre"],
                "district": row["district"],
                "is_free": _to_bool(row["is_free"]),
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "description": row["description"],
                "age_label": row["age_label"],
                "mood_tags": [],
                "mood_source": None,
                "status": _status(row["start_date"], row["end_date"], row["status"]),
                "days_left": max(0, (row["end_date"] - TODAY).days),
            },
        )

        keyword_type = row.get("keyword_type")
        keyword_value = row.get("keyword_value")
        if keyword_type == "MOOD" and keyword_value:
            event["mood_tags"].append(keyword_value)
            event["mood_source"] = event["mood_source"] or row.get("keyword_source")
        elif keyword_type == "AGE" and keyword_value and not event["age_label"]:
            event["age_label"] = keyword_value

    for event in events.values():
        if not event["mood_tags"]:
            event["mood_tags"] = ["default"]
        if not event["mood_source"]:
            event["mood_source"] = "db"
        if not event["age_label"]:
            event["age_label"] = "all"

    df = pd.DataFrame(events.values(), columns=EVENT_COLUMNS)
    if df.empty:
        return _empty_events_frame()
    return df[df["status"] != "CLOSED"].reset_index(drop=True)


def extract_preference_profile(selected_df: pd.DataFrame):
    genre_counter = Counter(selected_df["genre"].tolist())
    total_genre = sum(genre_counter.values()) or 1
    genre_weights = {genre: count / total_genre for genre, count in genre_counter.items()}

    mood_counter = Counter(
        mood for tags in selected_df["mood_tags"] for mood in tags
    )
    total_mood = sum(mood_counter.values()) or 1
    mood_weights = {mood: count / total_mood for mood, count in mood_counter.items()}
    allowed_ages = set(selected_df["age_label"].tolist())

    return genre_weights, mood_weights, allowed_ages


def score_all(df: pd.DataFrame, genre_weights: dict, mood_weights: dict) -> pd.DataFrame:
    df = df.copy()
    weights = WEIGHTS_DISPERSED if len(genre_weights) >= 3 else WEIGHTS_FOCUSED

    df["genre_score"] = df["genre"].apply(lambda genre: genre_weights.get(genre, 0.0))
    df["mood_score"] = df["mood_tags"].apply(
        lambda tags: min(sum(mood_weights.get(tag, 0.0) for tag in tags), 1.0)
    )

    df["urgency"] = 0.0
    active_mask = df["status"].isin(["ONGOING", "CLOSING_SOON"])
    imminent_mask = active_mask & (df["days_left"] <= 7)
    not_imminent_mask = active_mask & (df["days_left"] > 7)

    df.loc[imminent_mask, "urgency"] = 1.0
    df.loc[not_imminent_mask, "urgency"] = (
        1.0 - df.loc[not_imminent_mask, "days_left"] / 90
    ).clip(lower=0.0)

    df["score"] = (
        weights["genre"] * df["genre_score"]
        + weights["mood"] * df["mood_score"]
        + weights["urgency"] * df["urgency"]
    ).round(4)

    max_score = df["score"].max()
    min_score = df["score"].min()
    score_range = max_score - min_score
    if score_range > 0:
        df["match_pct"] = ((df["score"] - min_score) / score_range * 100).round(1)
    else:
        df["match_pct"] = 100.0

    df["genre_score"] = df["genre_score"].round(2)
    df["mood_score"] = df["mood_score"].round(2)
    df["urgency"] = df["urgency"].round(2)
    return df.sort_values("score", ascending=False).reset_index(drop=True)
