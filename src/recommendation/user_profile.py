"""
user_profile.py
──────────────────────────────────────────────────────────────────────────────
온보딩 샘플링 및 유저 프로필 빌드 로직

공개 함수
  - filter_by_age      : 유저 연령 기준 관람 불가 행사 하드 필터링
  - sample_onboarding  : 온보딩용 행사 장르별 균등 샘플링 (50건)
  - build_user_profile : 선택 행사 메타데이터 → 취향 프로필 딕셔너리 생성

설계 결정 사항
  - 게스트(age=None) → DEFAULT_AGE_GUEST(15) 자동 적용
  - reliability 컬럼값: BEST / HIGH / MID / LOW (영문 대문자)
  - LOW 신뢰도 행사: 샘플링 풀에서 제외
  - 종료된 행사: 취향 수집 목적이므로 포함
  - 대표이미지 없는 행사: 샘플링 풀에서 제외
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import warnings
from typing import Optional

import pandas as pd


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────

DEFAULT_AGE_GUEST: int = 15       # 비회원 또는 연령 미제공 시 기본 적용 연령
ONBOARDING_SAMPLE_SIZE: int = 20  # 온보딩 제공 행사 수 (유저가 이 중 5개 이상 선택)

# reliability 컬럼값 → 샘플링 가중치
#   LOW(0.0) : 분류기 기본값 출처, 별도 검수 권장 → 샘플링 풀 제외
#   MID(1.0) : 분류기 선택
#   HIGH(2.0): 규칙+분류기 일치 / 분류기+임베딩 일치
#   BEST(3.0): KOPIS 직접 매핑
LABEL_WEIGHT_MAP: dict[str, float] = {
    "BEST": 3.0,
    "HIGH": 2.0,
    "MID":  1.0,
    "LOW":  0.0,  # 명시적 제거 후 미사용
}

_ADULT_KEYWORDS: set[str] = {"청소년관람불가", "19세이상", "18세이상", "성인"}
_AGE_PATTERN: re.Pattern = re.compile(r"(\d+)\s*세\s*이상")


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _parse_min_age(raw: str | float) -> int:
    """
    관람등급 문자열 → 최소 관람 연령(int) 변환.

    처리 규칙
      NaN / 빈 값         → 0  (전체 허용)
      "전체관람가"         → 0
      "7세 이상"           → 7
      "청소년관람불가"     → 18
      미인식 문자열        → 0  (보수적 허용)
    """
    if pd.isna(raw) or str(raw).strip() == "":
        return 0

    s = str(raw).strip().replace(" ", "")

    if any(kw in s for kw in _ADULT_KEYWORDS):
        return 18

    m = _AGE_PATTERN.search(s)
    if m:
        return int(m.group(1))

    return 0


def _explode_tag_column(df: pd.DataFrame, col: str) -> pd.Series:
    """
    다중 태그 컬럼(리스트 또는 쉼표 구분 문자열) → 개별 태그 Series 변환.
    빈 문자열 제외.
    """
    series = df[col].dropna()
    if series.empty:
        return pd.Series(dtype=str)

    first_valid = series.iloc[0]
    if isinstance(first_valid, list):
        exploded = series.explode().astype(str).str.strip()
    else:
        exploded = series.astype(str).str.split(",").explode().str.strip()

    return exploded[exploded != ""]


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def filter_by_age(
    df: pd.DataFrame,
    age: Optional[int] = None,
) -> pd.DataFrame:
    """
    유저 연령 기준 관람 불가 행사 하드 필터링.

    Parameters
    ----------
    df  : 전체 행사 데이터프레임. `age_rating` 컬럼 필요.
    age : 유저 연령(int). None 또는 0 이하 → DEFAULT_AGE_GUEST(15) 적용.
          게스트(비회원) 포함 연령 미확인 케이스 모두 처리.

    Returns
    -------
    관람 가능 행사만 포함한 데이터프레임 (인덱스 리셋).

    Notes
    -----
    `age_rating` 컬럼 부재 시 경고 후 원본 반환 (파이프라인 중단 방지).
    """
    effective_age: int = (
        age if isinstance(age, int) and age > 0 else DEFAULT_AGE_GUEST
    )

    if "age_rating" not in df.columns:
        warnings.warn(
            "[filter_by_age] 'age_rating' 컬럼이 없습니다. "
            "연령 필터를 건너뜁니다.",
            UserWarning,
            stacklevel=2,
        )
        return df.copy()

    min_ages = df["age_rating"].apply(_parse_min_age)
    return df[min_ages <= effective_age].reset_index(drop=True)


def sample_onboarding(
    df: pd.DataFrame,
    age: Optional[int] = None,
    n: int = ONBOARDING_SAMPLE_SIZE,
    random_state: Optional[int] = 42,
) -> pd.DataFrame:
    """
    온보딩용 행사 샘플링.

    처리 순서
      1. filter_by_age          — 연령 하드 필터 (게스트 → DEFAULT_AGE_GUEST)
      2. 대표이미지 없는 행사 제거  — image_url 컬럼 기준
      3. reliability "LOW" 제거   — 신뢰도 낮음 행사 제외
      4. 신뢰도 가중치 부여        — BEST/HIGH/MID 가중치 적용
      5. 장르별 균등 비율 샘플링   — genre 컬럼 기준
         ※ 종료된 행사 포함 (취향 수집 목적)
      6. remainder 보충           — 미선택 풀에서 추가 샘플링

    Parameters
    ----------
    df           : 전체 행사 데이터프레임
    age          : 유저 연령. None → DEFAULT_AGE_GUEST 적용.
    n            : 샘플 목표 건수 (기본 50)
    random_state : 재현성 시드

    Returns
    -------
    샘플링된 행사 데이터프레임 (인덱스 리셋, _sample_weight 컬럼 제거).
    """
    # ── 1. 연령 하드 필터
    pool = filter_by_age(df, age)

    # ── 2. 대표이미지 없는 행사 제거
    if "image_url" in pool.columns:
        has_image = pool["image_url"].notna() & (pool["image_url"].str.strip() != "")
        pool = pool[has_image]

    # ── 3. LOW 제거 + 4. 가중치 부여
    pool = pool.copy()
    if "reliability" in pool.columns:
        pool = pool[pool["reliability"] != "LOW"]
        pool["_sample_weight"] = (
            pool["reliability"].map(LABEL_WEIGHT_MAP).fillna(1.0)
        )
    else:
        pool["_sample_weight"] = 1.0

    if pool.empty:
        warnings.warn(
            "[sample_onboarding] 필터 후 샘플링 가능한 행사가 없습니다.",
            UserWarning,
            stacklevel=2,
        )
        return pool.drop(columns=["_sample_weight"], errors="ignore")

    # ── 5. 장르별 균등 샘플링
    genre_col = "genre" if "genre" in pool.columns else None

    if genre_col is None:
        k = min(n, len(pool))
        sampled = pool.sample(n=k, weights="_sample_weight", random_state=random_state)
        return sampled.drop(columns=["_sample_weight"]).reset_index(drop=True)

    genres = pool[genre_col].dropna().unique()
    per_genre = max(1, n // len(genres))

    frames: list[pd.DataFrame] = []
    for genre in genres:
        sub = pool[pool[genre_col] == genre]
        k = min(per_genre, len(sub))
        if k == 0:
            continue
        frames.append(
            sub.sample(n=k, weights="_sample_weight", random_state=random_state)
        )

    # ── 6. remainder 보충
    if frames:
        sampled_idx = pd.concat(frames).index
        leftover = pool.drop(index=sampled_idx)
        remainder = n - sum(len(f) for f in frames)
        if remainder > 0 and not leftover.empty:
            k = min(remainder, len(leftover))
            frames.append(
                leftover.sample(
                    n=k, weights="_sample_weight", random_state=random_state
                )
            )

    result = pd.concat(frames) if frames else pool.iloc[:0]
    return result.drop(columns=["_sample_weight"]).reset_index(drop=True)


def build_user_profile(selected_events: pd.DataFrame) -> dict:
    """
    온보딩 선택 행사 메타데이터 → 취향 프로필 딕셔너리 생성.

    Returns
    -------
    {
        "genre":    {"전시/미술": 0.6, "클래식": 0.4},
        "subgenre": {"기획/테마 전시": 0.5, ...},
        "mood":     {"힐링/감성": 0.4, "감동/웅장": 0.3, ...},
    }
    각 값은 선택 행사 내 비중 (0~1, 합계 1.0).

    Notes
    -----
    - subgenre, mood: 다중 태그 (쉼표 구분 문자열 또는 list) 지원
    - 컬럼 부재 시 해당 키는 빈 딕셔너리 반환
    """
    if selected_events.empty:
        return {"genre": {}, "subgenre": {}, "mood": {}}

    def _normalize(series: pd.Series) -> dict:
        if series.empty:
            return {}
        return series.value_counts(normalize=True).to_dict()

    return {
        "genre": _normalize(
            selected_events["genre"].dropna()
            if "genre" in selected_events.columns
            else pd.Series(dtype=str)
        ),
        "subgenre": _normalize(
            _explode_tag_column(selected_events, "subgenre")
            if "subgenre" in selected_events.columns
            else pd.Series(dtype=str)
        ),
        "mood": _normalize(
            _explode_tag_column(selected_events, "mood")
            if "mood" in selected_events.columns
            else pd.Series(dtype=str)
        ),
    }