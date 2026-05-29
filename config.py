from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _parse_jdbc_mysql_url(jdbc_url: str) -> tuple[str, int, str]:
    prefix = "jdbc:mysql://"
    if not jdbc_url.startswith(prefix):
        raise ValueError("GCP_DB_URL must start with jdbc:mysql://")

    parsed = urlparse("mysql://" + jdbc_url[len(prefix):])
    if not parsed.hostname:
        raise ValueError("GCP_DB_URL must include a host")

    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("GCP_DB_URL must include a database name")

    return parsed.hostname, parsed.port or 3306, database


@lru_cache(maxsize=1)
def get_db_config() -> dict:
    jdbc_url = os.getenv("GCP_DB_URL")
    if jdbc_url:
        host, port, database = _parse_jdbc_mysql_url(jdbc_url)
    else:
        host = os.getenv("DB_HOST", "10.54.0.3")
        port = int(os.getenv("DB_PORT", "3306"))
        database = os.getenv("DB_NAME", "arbit-mysql")

    return {
        "host": host,
        "port": port,
        "user": os.getenv("GCP_DB_USERNAME", os.getenv("DB_USER", "root")),
        "password": os.getenv("GCP_DB_PASSWORD", os.getenv("DB_PASSWORD", "")),
        "db": database,
        "charset": "utf8mb4",
    }


@lru_cache(maxsize=1)
def get_gcs_config() -> dict[str, str]:
    bucket_name = os.getenv("GCS_BUCKET_NAME", "deepflow-image-storage")
    public_base_url = os.getenv(
        "GCS_PUBLIC_BASE_URL",
        f"https://storage.googleapis.com/{bucket_name}",
    ).rstrip("/")

    return {
        "bucket_name": bucket_name,
        "public_base_url": public_base_url,
    }


def build_gcs_public_url(object_name: str) -> str:
    config = get_gcs_config()
    return f"{config['public_base_url']}/{object_name.lstrip('/')}"


def get_gcs_bucket():
    from google.cloud import storage

    config = get_gcs_config()
    return storage.Client().bucket(config["bucket_name"])
