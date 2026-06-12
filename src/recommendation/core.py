"""
core.py
──────────────────────────────────────────────────────────────────────────────
콘텐츠 기반 필터링(CBF) 점수 계산 핵심 로직

공개 함수
  - urgency_score  : 행사 마감 임박도 스코어 (0.0 ~ 1.0)
  - content_score  : 유저 프로필 × 행사 적합도 스코어 → (total, breakdown) 튜플

설계 결정 사항
  - urgency 기준일: 상수로 모듈 내 선언 (전시/미술·교육/체험 180일, 기타 90일)
  - 마감일 초과 행사: 즉시 0.0 반환 (BE가 DB에서 closed 처리, 방어 코드 유지)
  - content_score: 항상 (total_score, score_breakdown) 튜플 반환
    → debug_mode 분기는 run_recommend.py에서 처리
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date
from typing import Optional


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────

# 긴급도 기준일 (일수)
URGENCY_BASE_LONG: int = 180   # 전시/미술, 교육/체험
URGENCY_BASE_SHORT: int = 90   # 기타 장르

LONG_URGENCY_GENRES: frozenset[str] = frozenset({"전시/미술", "교육/체험"})

# 콘텐츠 스코어 가중치 (합계 = 1.0)
WEIGHT_GENRE: float    = 0.30
WEIGHT_SUBGENRE: float = 0.15
WEIGHT_MOOD: float     = 0.35
WEIGHT_URGENCY: float  = 0.20


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def urgency_score(
    event: dict,
    today: Optional[date] = None,
) -> float:
    """
    행사 마감 임박도 스코어.

    계산식: max(0, 1 - 남은일수 / 기준일수)
      - 전시/미술, 교육/체험: 기준일 180일
      - 기타 장르:            기준일 90일

    Parameters
    ----------
    event : 행사 딕셔너리. 'end_date'(date), 'genre'(str) 키 사용.
    today : 기준일. None → date.today() 자동 적용.

    Returns
    -------
    0.0 ~ 1.0 사이 float.
    마감일 초과(closed) 또는 end_date 없음 → 0.0.
    """
    if today is None:
        today = date.today()

    end_date = event.get("end_date")
    if end_date is None:
        return 0.0

    # BE가 closed 처리하지만, 음수 방어 코드 유지
    remaining = (end_date - today).days
    if remaining < 0:
        return 0.0

    genre = event.get("genre", "")
    base_days = (
        URGENCY_BASE_LONG
        if genre in LONG_URGENCY_GENRES
        else URGENCY_BASE_SHORT
    )

    return round(max(0.0, 1.0 - remaining / base_days), 4)


def content_score(
    event: dict,
    profile: dict,
    today: Optional[date] = None,
) -> tuple[float, dict]:
    """
    유저 프로필 × 행사 간 콘텐츠 기반 적합도 점수.

    가중치
      무드(0.35) + 장르(0.30) + 긴급도(0.20) + 소분류(0.15)

    Parameters
    ----------
    event   : 행사 딕셔너리.
              'genre'(str), 'subgenre'(str|list), 'mood'(str|list),
              'end_date'(date) 키 사용.
    profile : build_user_profile() 반환값.
              {"genre": {...}, "subgenre": {...}, "mood": {...}}
    today   : 긴급도 기준일. None → date.today() 자동 적용.

    Returns
    -------
    (total_score, score_breakdown) 튜플.
      total_score    : 0.0 ~ 1.0 최종 점수 (소수점 4자리)
      score_breakdown: 요소별 점수 딕셔너리 (Ablation Study용)

    Notes
    -----
    - subgenre: 다중 태그 → max 적용 (가장 잘 맞는 소분류 1개 반영)
    - mood    : 다중 태그 → mean 적용 (전체 무드 일치도 평균)
    """
    # ── 장르 점수
    genre = event.get("genre", "")
    g_score = float(profile.get("genre", {}).get(genre, 0.0))

    # ── 소분류 점수 (max)
    subgenre = event.get("subgenre", [])
    if isinstance(subgenre, str):
        subgenre = [s.strip() for s in subgenre.split(",") if s.strip()]
    sg_vals = [
        float(profile.get("subgenre", {}).get(s, 0.0))
        for s in subgenre
    ]
    sg_score = max(sg_vals) if sg_vals else 0.0

    # ── 무드 점수 (mean)
    mood = event.get("mood", [])
    if isinstance(mood, str):
        mood = [m.strip() for m in mood.split(",") if m.strip()]
    m_vals = [
        float(profile.get("mood", {}).get(m, 0.0))
        for m in mood
    ]
    m_score = sum(m_vals) / len(m_vals) if m_vals else 0.0

    # ── 긴급도 점수
    urg = urgency_score(event, today)

    # ── 가중 합산
    total = (
        g_score  * WEIGHT_GENRE +
        sg_score * WEIGHT_SUBGENRE +
        m_score  * WEIGHT_MOOD +
        urg      * WEIGHT_URGENCY
    )

    breakdown = {
        "genre_score":    round(g_score, 4),
        "subgenre_score": round(sg_score, 4),
        "mood_score":     round(m_score, 4),
        "urgency_score":  round(urg, 4),
        "total_score":    round(total, 4),
    }

    return round(total, 4), breakdown
