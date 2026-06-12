"""
run_recommend.py
──────────────────────────────────────────────────────────────────────────────
추천 파이프라인 실행 진입점

외부(FastAPI 엔드포인트 등)에서 recommend()를 호출하여 사용.

파이프라인 흐름
  1. filter_by_age           — 연령 하드 필터 (게스트 → DEFAULT_AGE_GUEST)
  2. content_score           — 전체 행사 CBF 스코어링
  3. is_cf_ready 분기        — 조건 충족 시 CF 0.4 혼합, 미충족 시 CBF 단독
  4. 동점자 보정 정렬         — 총점 → 긴급도 → 시작일 최신순
  5. 취향 매칭 7건 추출       — 상위 스코어 기준
  6. 의외성 3건 추출          — 무드 일치 + 완전 미경험 장르
  7. debug_mode 응답 제어    — True 시 score_breakdown 포함
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from .core import content_score, urgency_score, WEIGHT_URGENCY
from .cf_utils import (
    is_cf_ready,
    get_cf_scores,
    HYBRID_CBF_WEIGHT,
    HYBRID_CF_WEIGHT,
)
from .user_profile import filter_by_age
from .schemas import EventRecommended, RecommendResponse, ScoreBreakdown


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────

TOP_CURATED: int     = 7    # 취향 매칭 건수
TOP_SERENDIPITY: int = 3    # 의외성 건수
TOP_MOOD_REF: int    = 2    # 의외성 기준 프로필 무드 상위 N개


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _to_mood_list(mood_value) -> list[str]:
    """mood 컬럼값 → 정제된 문자열 리스트 변환."""
    if isinstance(mood_value, list):
        return [m.strip() for m in mood_value if str(m).strip()]
    return [m.strip() for m in str(mood_value).split(",") if m.strip()]

def _row_to_event(
    row: dict,
    final_score: float,
    debug_mode: bool,
    description: Optional[str] = None,
) -> EventRecommended:
    """행사 딕셔너리 + 점수 → EventRecommended 변환."""
    breakdown = None
    if debug_mode and "_breakdown" in row:
        breakdown = ScoreBreakdown(**row["_breakdown"])

    return EventRecommended(
        event_id    = row["event_id"],
        title       = row.get("title", ""),
        genre       = row.get("genre", ""),
        mood        = _to_mood_list(row.get("mood", [])),
        end_date    = row.get("end_date"),
        total_score = round(final_score, 4),
        description = description,
        score_breakdown = breakdown,
    )


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def recommend(
    df: pd.DataFrame,
    profile: dict,
    age: Optional[int] = None,
    user_id: Optional[int] = None,
    interaction_matrix=None,
    user_index: Optional[dict] = None,
    event_index: Optional[dict] = None,
    debug_mode: bool = False,
    today: Optional[date] = None,
) -> RecommendResponse:
    """
    최종 추천 파이프라인.

    Parameters
    ----------
    df                : 전체 행사 데이터프레임 (DB 로드 상태)
    profile           : build_user_profile() 반환값
    age               : 유저 연령. None → DEFAULT_AGE_GUEST(15) 적용 (게스트 포함)
    user_id           : 로그인 유저 ID. 게스트 → None
    interaction_matrix: CF 상호작용 행렬. None → CBF 단독 실행
    user_index        : {user_id: row_idx}
    event_index       : {event_id: col_idx}
    debug_mode        : True 시 응답에 score_breakdown 포함
    today             : 긴급도 기준일. None → date.today() 자동 적용

    Returns
    -------
    RecommendResponse
      - curated     : 취향 매칭 상위 7건
      - serendipity : 의외성 3건 (무드 일치 + 완전 미경험 장르)
      - is_hybrid   : CF 하이브리드 적용 여부
    """
    if today is None:
        today = date.today()

    # ── 1. 연령 하드 필터 ─────────────────────────────────────────
    pool = filter_by_age(df, age)

    if pool.empty:
        return RecommendResponse(
            user_id=user_id, curated=[], serendipity=[], is_hybrid=False
        )

    # ── 2. 전체 CBF 스코어링 ─────────────────────────────────────
    scored_rows: list[dict] = []
    for _, row in pool.iterrows():
        event = row.to_dict()
        cbf_total, breakdown = content_score(event, profile, today)
        scored_rows.append({
            **event,
            "_cbf_score": cbf_total,
            "_breakdown": breakdown,
        })

    scored_df = pd.DataFrame(scored_rows)

    # ── 3. CF 분기 ────────────────────────────────────────────────
    use_hybrid = (
        interaction_matrix is not None
        and user_id is not None
        and user_index is not None
        and event_index is not None
        and is_cf_ready(interaction_matrix)
    )

    if use_hybrid:
        cf_map = get_cf_scores(
            user_id,
            scored_df["event_id"].tolist(),
            interaction_matrix,
            user_index,
            event_index,
        )
        scored_df["_final_score"] = (
            scored_df["_cbf_score"] * HYBRID_CBF_WEIGHT
            + scored_df["event_id"].map(cf_map).fillna(0.0) * HYBRID_CF_WEIGHT
        )
    else:
        scored_df["_final_score"] = scored_df["_cbf_score"]

    # ── 4. 동점자 보정 정렬 ───────────────────────────────────────
    # 1순위: _final_score 내림차순
    # 2순위: urgency_score 내림차순
    # 3순위: start_date 내림차순 (최신순, 컬럼 없으면 무시)
    scored_df["_urg_score"] = scored_df.apply(
        lambda r: urgency_score(r.to_dict(), today), axis=1
    )

    sort_cols = ["_final_score", "_urg_score"]
    sort_asc  = [False, False]
    if "start_date" in scored_df.columns:
        sort_cols.append("start_date")
        sort_asc.append(False)

    scored_df = scored_df.sort_values(
        by=sort_cols, ascending=sort_asc
    ).reset_index(drop=True)

    # ── 5. 취향 매칭 7건 ─────────────────────────────────────────
    curated_df  = scored_df.head(TOP_CURATED)
    curated_ids = set(curated_df["event_id"].tolist())

    curated_list = [
        _row_to_event(r, r["_final_score"], debug_mode)
        for r in curated_df.to_dict("records")
    ]

    # ── 6. 의외성 3건 ────────────────────────────────────────────
    # 조건: 프로필 무드 상위 2개 중 1개 이상 일치
    #       + 완전 미경험 장르 (profile["genre"] 에 없는 장르)
    top_moods: set[str] = {
        m for m, _ in sorted(
            profile.get("mood", {}).items(), key=lambda x: x[1], reverse=True
        )[:TOP_MOOD_REF]
    }

    profile_genres: set[str] = set(profile.get("genre", {}).keys())
    all_genres: set[str]     = set(scored_df["genre"].unique())
    zero_genres: set[str]    = all_genres - profile_genres

    # zero_genres 없으면 가중치 최하위 장르 폴백
    if not zero_genres and profile.get("genre"):
        min_weight = min(profile["genre"].values())
        zero_genres = {
            g for g, w in profile["genre"].items() if w == min_weight
        }

    remaining_df = scored_df[~scored_df["event_id"].isin(curated_ids)]

    def _has_top_mood(mood_val) -> bool:
        return bool(top_moods & set(_to_mood_list(mood_val)))

    serendipity_df = remaining_df[
        remaining_df["genre"].isin(zero_genres)
        & remaining_df["mood"].apply(_has_top_mood)
    ].head(TOP_SERENDIPITY)

    serendipity_list = [
        _row_to_event(r, r["_final_score"], debug_mode)
        for r in serendipity_df.to_dict("records")
    ]

    # ── 7. 응답 반환 ─────────────────────────────────────────────
    return RecommendResponse(
        user_id     = user_id,
        curated     = curated_list,
        serendipity = serendipity_list,
        is_hybrid   = use_hybrid,
    )