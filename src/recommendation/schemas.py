"""
schemas.py
──────────────────────────────────────────────────────────────────────────────
FastAPI 요청/응답 데이터 구조 정의 (Pydantic v2)

모델 목록
  - RecommendRequest  : POST /recommend 요청 바디
  - ScoreBreakdown    : 요소별 점수 상세 (debug_mode=True 시 포함)
  - EventRecommended  : 추천 행사 단일 항목
  - RecommendResponse : POST /recommend 응답 바디
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    """
    POST /recommend 요청 바디.

    Fields
    ------
    user_id    : 로그인 유저 ID. 비회원(게스트) → None.
    age        : 유저 연령. None → DEFAULT_AGE_GUEST(15) 자동 적용.
    profile    : build_user_profile() 반환 딕셔너리.
    debug_mode : True 시 응답에 score_breakdown 포함.
    """
    user_id:    Optional[int]  = Field(None,  description="로그인 유저 ID. 게스트 시 None.")
    age:        Optional[int]  = Field(None,  description="유저 연령. None → DEFAULT_AGE_GUEST 적용.")
    profile:    dict           = Field(...,   description="build_user_profile() 반환 딕셔너리.")
    debug_mode: bool           = Field(False, description="True 시 score_breakdown 응답에 포함.")


class ScoreBreakdown(BaseModel):
    """
    콘텐츠 기반 요소별 점수 상세.
    debug_mode=True 일 때만 EventRecommended.score_breakdown 에 포함.
    Ablation Study 스크립트에서도 이 구조를 재사용.
    """
    genre_score:    float = Field(..., description="장르 일치 점수 (가중치 0.30 적용 전)")
    subgenre_score: float = Field(..., description="소분류 일치 점수 (가중치 0.15 적용 전)")
    mood_score:     float = Field(..., description="무드 일치 점수 (가중치 0.35 적용 전)")
    urgency_score:  float = Field(..., description="긴급도 점수 (가중치 0.20 적용 전)")
    total_score:    float = Field(..., description="가중 합산 최종 점수")


class EventRecommended(BaseModel):
    """
    추천 결과 단일 행사 항목.

    Fields
    ------
    description    : 의외성(serendipity) 행사에만 자동 생성된 설명 문구 포함.
                     취향 매칭(curated) 행사 → None.
    score_breakdown: debug_mode=True 일 때만 포함.
    """
    event_id:       str
    title:          str
    genre:          str
    mood:           list[str]
    end_date:       Optional[date]   = None
    total_score:    float
    description:    Optional[str]    = Field(None, description="의외성 행사 설명 문구.")
    score_breakdown: Optional[ScoreBreakdown] = Field(
        None, description="debug_mode=True 시 포함."
    )


class RecommendResponse(BaseModel):
    """
    POST /recommend 응답 바디.

    Fields
    ------
    user_id     : 요청 유저 ID (게스트 → None).
    curated     : 취향 매칭 상위 7건.
    serendipity : 의외성 3건 (무드 일치 + 완전 미경험 장르).
    is_hybrid   : CF 하이브리드 모드 적용 여부 (로드맵 확인용).
    """
    user_id:     Optional[int]
    curated:     list[EventRecommended] = Field(..., description="취향 매칭 상위 7건.")
    serendipity: list[EventRecommended] = Field(..., description="의외성 3건.")
    is_hybrid:   bool                   = Field(False, description="CF 하이브리드 적용 여부.")