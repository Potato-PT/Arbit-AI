from __future__ import annotations

import unittest
from datetime import date
from urllib.parse import urlencode

import pandas as pd
from fastapi.testclient import TestClient

import app as app_module


def _sample_events_df() -> pd.DataFrame:
    rows = [
        ("클래식", "영등포구", "영등포 마티네콘서트", "2026-10-15", "2026-10-15"),
        ("클래식", "마포구", "선율 피아노 리사이틀", "2026-09-16", "2026-09-16"),
        ("콘서트", "마포구", "MAC 모닝 콘서트 6", "2026-08-26", "2026-08-26"),
        ("무용", "영등포구", "해설이 있는 고전발레", "2026-08-22", "2026-08-22"),
        ("전시/미술", "강남구", "핸드아티코리아", "2026-08-13", "2026-08-16"),
        ("축제-문화/예술", "종로구", "종로 문화예술 축제", "2026-06-10", "2026-06-20"),
        ("교육/체험", "강서구", "어린이 문화 체험", "2026-07-01", "2026-07-31"),
        ("국악", "서초구", "토요 국악 한마당", "2026-06-05", "2026-06-05"),
        ("연극", "중구", "서울 연극 산책", "2026-06-12", "2026-07-12"),
        ("뮤지컬/오페라", "송파구", "여름 오페라 갈라", "2026-07-20", "2026-07-21"),
        ("독주/독창회", "용산구", "첼로 독주회", "2026-09-01", "2026-09-01"),
        ("기타", "성동구", "동네 문화 살롱", "2026-06-25", "2026-08-30"),
    ]
    df = pd.DataFrame(
        [
            {
                "분류": category,
                "자치구": district,
                "공연/행사명": title,
                "날짜": f"{start}~{end}",
                "장소": f"{district} 문화공간",
                "기관명": "테스트기관",
                "이용대상": "누구나",
                "이용요금": "무료",
                "시작일": f"{start} 00:00:00.0",
                "종료일": f"{end} 00:00:00.0",
                "테마분류": "기타",
                "유무료": "무료",
                "문화포털상세URL": "https://example.com/events",
                "대표이미지": "https://example.com/image.jpg",
                "행사시간": "10:00",
            }
            for category, district, title, start, end in rows
        ]
    )
    df["_start_date"] = pd.to_datetime(df["시작일"], errors="coerce").dt.date
    df["_end_date"] = pd.to_datetime(df["종료일"], errors="coerce").dt.date
    return df


SEARCH_CASES = [
    {"id": "all_events", "params": {}, "description": "사용자는 분류와 자치구를 지정하지 않고 전체 서울 문화행사를 마감일이 빠른 순서로 검색했다."},
    {"id": "classic_all", "params": {"category": "클래식"}, "description": "사용자는 모든 자치구에서 클래식 행사만 검색했다."},
    {"id": "concert_all", "params": {"category": "콘서트"}, "description": "사용자는 모든 자치구에서 콘서트 행사만 검색했다."},
    {"id": "exhibition_all", "params": {"category": "전시/미술"}, "description": "사용자는 모든 자치구에서 전시/미술 행사만 검색했다."},
    {"id": "mapo_all", "params": {"district": ["마포구"]}, "description": "사용자는 마포구에서 열리는 모든 분류의 행사를 검색했다."},
    {"id": "yeongdeungpo_all", "params": {"district": ["영등포구"]}, "description": "사용자는 영등포구에서 열리는 모든 분류의 행사를 검색했다."},
    {"id": "mapo_yeongdeungpo", "params": {"district": ["마포구", "영등포구"]}, "description": "사용자는 마포구와 영등포구에서 열리는 행사를 함께 검색했다."},
    {"id": "gangnam_jongno", "params": {"district": ["강남구", "종로구"]}, "description": "사용자는 강남구와 종로구의 문화행사를 함께 검색했다."},
    {"id": "from_august", "params": {"startDate": "2026-08-01"}, "description": "사용자는 2026년 8월 1일 이후 시작하는 행사를 검색했다."},
    {"id": "until_august", "params": {"endDate": "2026-08-31"}, "description": "사용자는 2026년 8월 31일까지 종료되는 행사를 검색했다."},
    {"id": "july_window", "params": {"startDate": "2026-07-01", "endDate": "2026-07-31"}, "description": "사용자는 2026년 7월 안에 시작하고 종료되는 행사를 검색했다."},
    {"id": "summer_window", "params": {"startDate": "2026-06-01", "endDate": "2026-08-31"}, "description": "사용자는 2026년 6월부터 8월 말까지의 여름 시즌 행사를 검색했다."},
    {"id": "classic_mapo", "params": {"category": "클래식", "district": ["마포구"]}, "description": "사용자는 마포구에서 열리는 클래식 행사만 검색했다."},
    {"id": "classic_yeongdeungpo", "params": {"category": "클래식", "district": ["영등포구"]}, "description": "사용자는 영등포구에서 열리는 클래식 행사만 검색했다."},
    {"id": "concert_mapo_august", "params": {"category": "콘서트", "district": ["마포구"], "startDate": "2026-08-01", "endDate": "2026-08-31"}, "description": "사용자는 2026년 8월 중 마포구에서 열리는 콘서트 행사를 검색했다."},
    {"id": "dance_yeongdeungpo_august", "params": {"category": "무용", "district": ["영등포구"], "startDate": "2026-08-01", "endDate": "2026-08-31"}, "description": "사용자는 2026년 8월 중 영등포구에서 열리는 무용 행사를 검색했다."},
    {"id": "exhibition_gangnam_august", "params": {"category": "전시/미술", "district": ["강남구"], "startDate": "2026-08-01", "endDate": "2026-08-31"}, "description": "사용자는 2026년 8월 중 강남구에서 열리는 전시/미술 행사를 검색했다."},
    {"id": "festival_jongno_june", "params": {"category": "축제-문화/예술", "district": ["종로구"], "startDate": "2026-06-01", "endDate": "2026-06-30"}, "description": "사용자는 2026년 6월 중 종로구에서 열리는 문화예술 축제를 검색했다."},
    {"id": "education_gangseo_july", "params": {"category": "교육/체험", "district": ["강서구"], "startDate": "2026-07-01", "endDate": "2026-07-31"}, "description": "사용자는 2026년 7월 중 강서구에서 열리는 교육/체험 행사를 검색했다."},
    {"id": "gugak_seocho_june", "params": {"category": "국악", "district": ["서초구"], "startDate": "2026-06-01", "endDate": "2026-06-30"}, "description": "사용자는 2026년 6월 중 서초구에서 열리는 국악 행사를 검색했다."},
    {"id": "theater_junggu_summer", "params": {"category": "연극", "district": ["중구"], "startDate": "2026-06-01", "endDate": "2026-07-31"}, "description": "사용자는 2026년 6월부터 7월까지 중구에서 열리는 연극 행사를 검색했다."},
    {"id": "opera_songpa_july", "params": {"category": "뮤지컬/오페라", "district": ["송파구"], "startDate": "2026-07-01", "endDate": "2026-07-31"}, "description": "사용자는 2026년 7월 중 송파구에서 열리는 뮤지컬/오페라 행사를 검색했다."},
    {"id": "solo_yongsan_from_sep", "params": {"category": "독주/독창회", "district": ["용산구"], "startDate": "2026-09-01"}, "description": "사용자는 2026년 9월 1일 이후 용산구에서 열리는 독주/독창회 행사를 검색했다."},
    {"id": "etc_seongdong_until_aug", "params": {"category": "기타", "district": ["성동구"], "endDate": "2026-08-31"}, "description": "사용자는 2026년 8월 말까지 종료되는 성동구의 기타 분류 행사를 검색했다."},
    {"id": "classic_two_districts_from_sep", "params": {"category": "클래식", "district": ["마포구", "영등포구"], "startDate": "2026-09-01"}, "description": "사용자는 2026년 9월 이후 마포구와 영등포구에서 열리는 클래식 행사를 검색했다."},
    {"id": "mapo_until_sep", "params": {"district": ["마포구"], "endDate": "2026-09-30"}, "description": "사용자는 2026년 9월 말까지 종료되는 마포구 행사를 분류 제한 없이 검색했다."},
    {"id": "western_districts_summer", "params": {"district": ["강서구", "마포구", "영등포구"], "startDate": "2026-07-01", "endDate": "2026-08-31"}, "description": "사용자는 2026년 7월부터 8월까지 강서구, 마포구, 영등포구에서 열리는 행사를 검색했다."},
    {"id": "central_districts_june_july", "params": {"district": ["종로구", "중구", "용산구"], "startDate": "2026-06-01", "endDate": "2026-07-31"}, "description": "사용자는 2026년 6월부터 7월까지 종로구, 중구, 용산구의 행사를 검색했다."},
    {"id": "paid_like_late_year_classic", "params": {"category": "클래식", "startDate": "2026-09-01", "endDate": "2026-12-31"}, "description": "사용자는 2026년 9월부터 연말까지 열리는 클래식 행사를 자치구 제한 없이 검색했다."},
    {"id": "no_matching_category", "params": {"category": "영화", "district": ["마포구"], "startDate": "2026-08-01", "endDate": "2026-08-31"}, "description": "사용자는 2026년 8월 중 마포구에서 열리는 영화 행사를 검색했지만 조건에 맞는 결과가 없는 상황을 확인했다."},
]


def _request_path(params: dict) -> str:
    query = {"sort": "deadline", **params}
    return "/api/events?" + urlencode(query, doseq=True)


def _expected_rows(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    expected = df.copy()
    if category := params.get("category"):
        expected = expected[expected["분류"] == category]
    if districts := params.get("district"):
        expected = expected[expected["자치구"].isin(districts)]
    if start_date := params.get("startDate"):
        expected = expected[expected["_start_date"] >= date.fromisoformat(start_date)]
    if end_date := params.get("endDate"):
        expected = expected[expected["_end_date"] <= date.fromisoformat(end_date)]
    return expected.sort_values(["_end_date", "_start_date", "공연/행사명"], ascending=[True, True, True])


class EventSearchCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sample_df = _sample_events_df()
        cls.original_get_cultural_events_df = app_module.get_cultural_events_df
        app_module.get_cultural_events_df = lambda: cls.sample_df.copy()
        cls.client = TestClient(app_module.app)

    @classmethod
    def tearDownClass(cls) -> None:
        app_module.get_cultural_events_df = cls.original_get_cultural_events_df

    def test_registered_event_search_cases(self) -> None:
        self.assertEqual(30, len(SEARCH_CASES))

        for case in SEARCH_CASES:
            with self.subTest(case=case["id"], description=case["description"]):
                response = self.client.get(_request_path(case["params"]))

                self.assertEqual(200, response.status_code)
                payload = response.json()
                expected = _expected_rows(self.sample_df, case["params"])

                self.assertEqual("deadline", payload["sort"])
                self.assertEqual(len(expected), payload["total"])
                self.assertEqual(
                    expected["종료일"].map(lambda value: pd.to_datetime(value).date().isoformat()).tolist()[:20],
                    [event["end_date"] for event in payload["events"]],
                )

                for event in payload["events"]:
                    if category := case["params"].get("category"):
                        self.assertEqual(category, event["category"])
                    if districts := case["params"].get("district"):
                        self.assertIn(event["district"], districts)
                    if start_date := case["params"].get("startDate"):
                        self.assertGreaterEqual(event["start_date"], start_date)
                    if end_date := case["params"].get("endDate"):
                        self.assertLessEqual(event["end_date"], end_date)


if __name__ == "__main__":
    unittest.main()
