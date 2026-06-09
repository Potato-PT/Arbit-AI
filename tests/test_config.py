from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import config


class DbConfigTest(unittest.TestCase):
    def tearDown(self) -> None:
        config.get_db_config.cache_clear()

    def test_app_db_settings_take_precedence(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_DB_URL": "jdbc:mysql://arbit-db:3306/arbit?serverTimezone=Asia/Seoul&characterEncoding=UTF-8",
                "APP_DB_USERNAME": "arbit",
                "APP_DB_PASSWORD": "root",
                "GCP_DB_URL": "jdbc:mysql://example.com:3306/other",
                "GCP_DB_USERNAME": "other",
                "GCP_DB_PASSWORD": "other-password",
            },
            clear=True,
        ):
            config.get_db_config.cache_clear()

            db_config = config.get_db_config()

        self.assertEqual("arbit-db", db_config["host"])
        self.assertEqual(3306, db_config["port"])
        self.assertEqual("arbit", db_config["db"])
        self.assertEqual("arbit", db_config["user"])
        self.assertEqual("root", db_config["password"])

    def test_local_db_url_matches_arbit_local_script(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARBIT_DB_PROFILE": "local",
                "LOCAL_DB_URL": "jdbc:mysql://127.0.0.1:3306/arbit_local?serverTimezone=Asia/Seoul&characterEncoding=UTF-8",
                "LOCAL_DB_USERNAME": "root",
                "LOCAL_DB_PASSWORD": "root",
            },
            clear=True,
        ):
            config.get_db_config.cache_clear()

            db_config = config.get_db_config()

        self.assertEqual("127.0.0.1", db_config["host"])
        self.assertEqual(3306, db_config["port"])
        self.assertEqual("arbit_local", db_config["db"])
        self.assertEqual("root", db_config["user"])
        self.assertEqual("root", db_config["password"])


if __name__ == "__main__":
    unittest.main()
