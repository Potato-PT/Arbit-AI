"""
cf_utils.py
──────────────────────────────────────────────────────────────────────────────
협업 필터링(CF) 행렬 연산 및 조건 검증 로직

공개 함수
  - is_cf_ready   : CF 활성화 조건 충족 여부 검증
  - get_cf_scores : 유저-행사 CF 기반 점수 벡터 계산

설계 결정 사항 (인수인계_v3 확정)
  - 현재 콘텐츠 기반(CBF) 단독 운영
  - 조건 충족(유저 500명, 행사 200건, 밀도 5%) 시 CBF 0.6 + CF 0.4 하이브리드 자동 전환
  - CF 활성화 전까지 이 모듈은 is_cf_ready=False 반환만 수행
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# ─────────────────────────────────────────────
# CF 활성화 조건 상수
# ─────────────────────────────────────────────

CF_MIN_USERS: int   = 500    # 최소 유저 수
CF_MIN_EVENTS: int  = 200    # 최소 행사 수
CF_MIN_DENSITY: float = 0.05  # 최소 행렬 밀도 (5%)

# 하이브리드 가중치
HYBRID_CBF_WEIGHT: float = 0.6
HYBRID_CF_WEIGHT: float  = 0.4


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def is_cf_ready(interaction_matrix) -> bool:
    """
    CF 활성화 조건 충족 여부 검증.

    조건 (모두 충족 시 True)
      1. 유저 수   >= CF_MIN_USERS  (500명)
      2. 행사 수   >= CF_MIN_EVENTS (200건)
      3. 행렬 밀도 >= CF_MIN_DENSITY (5%)

    Parameters
    ----------
    interaction_matrix : scipy sparse matrix 또는 numpy ndarray.

    Returns
    -------
    bool. True → 하이브리드 모드, False → CBF 단독.
    """
    if interaction_matrix is None:
        return False

    try:
        n_users, n_events = interaction_matrix.shape

        # sparse matrix 여부 확인
        nnz = (
            interaction_matrix.nnz
            if hasattr(interaction_matrix, "nnz")
            else int(np.count_nonzero(interaction_matrix))
        )

        density = nnz / (n_users * n_events) if (n_users * n_events) > 0 else 0.0

        return (
            n_users  >= CF_MIN_USERS
            and n_events >= CF_MIN_EVENTS
            and density  >= CF_MIN_DENSITY
        )
    except Exception:
        return False


def get_cf_scores(
    user_id: int,
    event_ids: list[str],
    interaction_matrix,
    user_index: dict[int, int],
    event_index: dict[str, int],
) -> dict[str, float]:
    """
    특정 유저에 대한 CF 기반 행사별 점수 계산 (코사인 유사도 기반).

    Parameters
    ----------
    user_id           : 대상 유저 ID
    event_ids         : 점수를 계산할 행사 ID 목록
    interaction_matrix: 유저-행사 상호작용 행렬 (유저 행, 행사 열)
    user_index        : {user_id: matrix_row_idx} 매핑
    event_index       : {event_id: matrix_col_idx} 매핑

    Returns
    -------
    {event_id: cf_score(0.0~1.0)} 딕셔너리.
    행렬에 없는 유저/행사 → 0.0 반환.

    Notes
    -----
    - 유저 행 벡터와 행사 열 벡터 간 코사인 유사도로 점수 계산
    - is_cf_ready() True 시에만 호출됨 (조건 미충족 케이스 처리 불필요)
    """
    if user_id not in user_index:
        return {eid: 0.0 for eid in event_ids}

    user_row_idx = user_index[user_id]
    user_vector = np.asarray(interaction_matrix[user_row_idx]).flatten().astype(float)
    user_norm = np.linalg.norm(user_vector)

    scores: dict[int, float] = {}

    for event_id in event_ids:
        if event_id not in event_index:
            scores[event_id] = 0.0
            continue

        col_idx = event_index[event_id]
        event_vector = np.asarray(
            interaction_matrix[:, col_idx]
        ).flatten().astype(float)
        event_norm = np.linalg.norm(event_vector)

        if user_norm == 0.0 or event_norm == 0.0:
            scores[event_id] = 0.0
        else:
            cosine = np.dot(user_vector, event_vector) / (user_norm * event_norm)
            scores[event_id] = float(np.clip(cosine, 0.0, 1.0))

    return scores