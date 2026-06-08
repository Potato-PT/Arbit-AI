from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _parse_jdbc_mysql_url(jdbc_url: str, env_name: str = "APP_DB_URL") -> tuple[str, int, str]:
    prefix = "jdbc:mysql://"
    if not jdbc_url.startswith(prefix):
        raise ValueError(f"{env_name} must start with jdbc:mysql://")

    parsed = urlparse("mysql://" + jdbc_url[len(prefix):])
    if not parsed.hostname:
        raise ValueError(f"{env_name} must include a host")

    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError(f"{env_name} must include a database name")

    return parsed.hostname, parsed.port or 3306, database


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return default


@lru_cache(maxsize=1)
def get_db_config() -> dict:
    db_profile = os.getenv("ARBIT_DB_PROFILE", "").lower()
    app_db_url = os.getenv("APP_DB_URL")
    local_db_url = os.getenv("LOCAL_DB_URL")
    gcp_db_url = os.getenv("GCP_DB_URL")

    if app_db_url:
        host, port, database = _parse_jdbc_mysql_url(app_db_url, "APP_DB_URL")
        user = _first_env(
            "APP_DB_USERNAME",
            "LOCAL_DB_USERNAME",
            "MYSQL_USER",
            "DB_USER",
            "GCP_DB_USERNAME",
            default="root",
        )
        password = _first_env(
            "APP_DB_PASSWORD",
            "LOCAL_DB_PASSWORD",
            "MYSQL_PASSWORD",
            "DB_PASSWORD",
            "GCP_DB_PASSWORD",
        )
    elif db_profile == "local" and local_db_url:
        host, port, database = _parse_jdbc_mysql_url(local_db_url, "LOCAL_DB_URL")
        user = _first_env(
            "LOCAL_DB_USERNAME",
            "APP_DB_USERNAME",
            "DB_USER",
            "GCP_DB_USERNAME",
            default="root",
        )
        password = _first_env(
            "LOCAL_DB_PASSWORD",
            "APP_DB_PASSWORD",
            "DB_PASSWORD",
            "GCP_DB_PASSWORD",
        )
    elif db_profile == "gcp" or gcp_db_url:
        if not gcp_db_url:
            raise ValueError("GCP_DB_URL must be set when ARBIT_DB_PROFILE=gcp")
        host, port, database = _parse_jdbc_mysql_url(gcp_db_url, "GCP_DB_URL")
        user = _first_env("GCP_DB_USERNAME", "APP_DB_USERNAME", "DB_USER", default="root")
        password = _first_env("GCP_DB_PASSWORD", "APP_DB_PASSWORD", "DB_PASSWORD")
    else:
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = int(os.getenv("DB_PORT", "3306"))
        database = os.getenv("DB_NAME", "arbit_local")
        user = _first_env("DB_USER", "LOCAL_DB_USERNAME", "APP_DB_USERNAME", default="root")
        password = _first_env("DB_PASSWORD", "LOCAL_DB_PASSWORD", "APP_DB_PASSWORD")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "db": database,
        "charset": "utf8mb4",
    }


def is_local_db_profile() -> bool:
    return os.getenv("ARBIT_DB_PROFILE", "gcp").lower() == "local"


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
