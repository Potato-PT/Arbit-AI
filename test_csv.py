"""
test_csv.py
──────────────────────────────────────────────────────────────────────────────
CSV 기반 추천 파이프라인 빠른 테스트 스크립트

실행 방법
  python test_csv.py

수정이 필요한 곳
  1. CSV_PATH  : 실제 CSV 파일 경로 (기본값: data/03_final/events_with_mood.csv)
  2. TEST_AGE  : 테스트 유저 연령 (None → 게스트 / DEFAULT_AGE_GUEST=15 적용)
  3. SELECT_N  : 온보딩 20개 중 선택 시뮬레이션 건수 (최소 5 이상)
──────────────────────────────────────────────────────────────────────────────
"""

import sys
import types
import importlib.util
from datetime import date
from pathlib import Path

# ─────────────────────────────────────────────
# 패키지 임포트 설정
# ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent   # ARBIT-AI/ 루트
sys.path.insert(0, str(ROOT / "src"))

_pkg = types.ModuleType("recommendation")
_pkg.__path__ = [str(ROOT / "src" / "recommendation")]
_pkg.__package__ = "recommendation"
sys.modules.setdefault("recommendation", _pkg)

import pandas as pd

from recommendation.user_profile import sample_onboarding, build_user_profile
from recommendation.run_recommend import recommend


# ══════════════════════════════════════════════
# ✏️  수정 필요 구역
# ══════════════════════════════════════════════

CSV_PATH = ROOT / "data" / "03_final" / "events_with_mood.csv"

TEST_AGE: int = 25   # 테스트 유저 연령 (None → 게스트)
SELECT_N: int = 7    # 온보딩 20개 중 선택 시뮬레이션 건수 (최소 5 이상)

# ══════════════════════════════════════════════


# ─────────────────────────────────────────────
# CSV 컬럼명 → 파이프라인 기대 컬럼명 매핑
# (CSV 실제 컬럼명이 왼쪽, 파이프라인 기대값이 오른쪽)
# ─────────────────────────────────────────────
COL_MAP: dict[str, str] = {
    "공연ID":    "event_id",
    "제목":      "title",
    "장르":      "genre",
    "소분류":    "subgenre",
    "무드_태그":  "mood",
    "관람연령":   "age_rating",
    "대표이미지":  "image_url",
    "시작일":    "start_date",
    "종료일":    "end_date",
}

# 소분류_근거 텍스트 → reliability 변환
# (DB에는 BEST/HIGH/MID/LOW로 저장됨, CSV에서는 이 단계에서 파생)
REASON_TO_RELIABILITY: dict[str, str] = {
    "KOPIS 직접 매핑":      "BEST",
    "규칙+분류기 일치":     "HIGH",
    "분류기+임베딩 일치":   "HIGH",
    "규칙 우선(소개 부족)": "HIGH",
    "규칙 우선(소개 충분)": "HIGH",
    "분류기 선택":          "MID",
    "분류기 기본값":        "LOW",
}


# ─────────────────────────────────────────────
# CSV 로드 및 전처리
# ─────────────────────────────────────────────

def load_and_preprocess(path: Path) -> pd.DataFrame:
    """
    CSV 로드 + 파이프라인 입력 형식으로 전처리.

    처리 내용
      1. 컬럼 리네임 (COL_MAP)
      2. 무드 구분자 변환: '|' → ','   (CSV는 '|' 사용, 파이프라인은 ',' 기대)
      3. reliability 컬럼 파생: 소분류_근거 → BEST/HIGH/MID/LOW
         (DB 연동 시에는 이 단계 불필요, DB에 이미 저장됨)
      4. 날짜 컬럼 파싱: str → date
    """
    if not path.exists():
        print(f"[ERROR] CSV 파일을 찾을 수 없습니다:\n        {path}")
        print("        CSV_PATH 값을 실제 경로로 수정 후 재실행하세요.")
        sys.exit(1)

    df = pd.read_csv(path, low_memory=False)
    print(f"[로드] {len(df):,}건 | 컬럼 수: {len(df.columns)}")

    # 1. 컬럼 리네임
    df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})

    # 2. 무드 구분자 변환: '|' → ','
    if "mood" in df.columns:
        df["mood"] = df["mood"].str.replace("|", ",", regex=False)

    # 3. reliability 파생
    if "소분류_근거" in df.columns:
        df["reliability"] = (
            df["소분류_근거"].map(REASON_TO_RELIABILITY).fillna("MID")
        )
    else:
        print("[WARN] '소분류_근거' 컬럼 없음 → reliability 전체 MID 처리")
        df["reliability"] = "MID"

    # 4. 날짜 파싱
    for col in ("start_date", "end_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    return df


# ─────────────────────────────────────────────
# 출력 헬퍼
# ─────────────────────────────────────────────

def divider(title: str = "") -> None:
    print(f"\n{'─' * 60}")
    if title:
        print(f"  {title}")
        print("─" * 60)


def print_events(events, show_breakdown: bool = False) -> None:
    for e in events:
        end_str = f" | 마감: {e.end_date}" if e.end_date else ""
        print(f"  [{e.event_id}] {e.title[:40]}")
        print(f"        장르: {e.genre} | 무드: {', '.join(e.mood)}"
              f"{end_str} | 점수: {e.total_score:.4f}")
        if show_breakdown and e.score_breakdown:
            b = e.score_breakdown
            print(f"        └ 장르:{b.genre_score:.3f} "
                  f"소분류:{b.subgenre_score:.3f} "
                  f"무드:{b.mood_score:.3f} "
                  f"긴급도:{b.urgency_score:.3f}")
        if e.description:
            print(f"        → {e.description}")


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main() -> None:
    if SELECT_N < 5:
        print("[ERROR] SELECT_N은 최소 5 이상이어야 합니다.")
        sys.exit(1)

    print("=" * 60)
    print("  추천 파이프라인 CSV 테스트")
    print(f"  기준일 : {date.today()}")
    print(f"  유저 연령: {TEST_AGE if TEST_AGE else '게스트 (DEFAULT_AGE=15)'}")
    print("=" * 60)

    # ── 1. CSV 로드 및 전처리 ───────────────────────────────────
    df = load_and_preprocess(CSV_PATH)

    # ── 2. 온보딩 샘플링 (20건) ─────────────────────────────────
    divider("STEP 1 | 온보딩 샘플링 (20건)")
    sampled = sample_onboarding(df, age=TEST_AGE, n=20, random_state=42)
    print(f"  샘플 결과: {len(sampled)}건")
    if "genre" in sampled.columns:
        print("  장르 분포:")
        for genre, cnt in sampled["genre"].value_counts().items():
            print(f"    {genre}: {cnt}건")

    # ── 3. 유저 선택 시뮬레이션 ─────────────────────────────────
    # 실제 서비스: 유저가 화면에서 직접 선택 (5개 이상 강제)
    # 테스트: random.sample로 SELECT_N건 선택 시뮬레이션
    divider(f"STEP 2 | 유저 선택 시뮬레이션 ({SELECT_N}건 / 20건 중)")
    print("  ※ 실제 서비스에서는 유저가 직접 선택 (최소 5건 이상 선택 강제)")
    selected = sampled.sample(
        n=min(SELECT_N, len(sampled)), random_state=42
    ).reset_index(drop=True)
    for _, row in selected.iterrows():
        print(f"  ✓ [{row.get('event_id', '?')}] "
              f"{str(row.get('title', '?'))[:42]} ({row.get('genre', '?')})")

    # ── 4. 유저 프로필 빌드 ─────────────────────────────────────
    divider("STEP 3 | 유저 프로필 빌드")
    profile = build_user_profile(selected)
    for key, weights in profile.items():
        if weights:
            top3 = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
            print(f"  {key:8s}: " + ", ".join(f"{k}({v:.2f})" for k, v in top3))

    # ── 5. 추천 실행 ────────────────────────────────────────────
    divider("STEP 4 | 추천 실행 (최대 10건)")
    result = recommend(
        df         = df,
        profile    = profile,
        age        = TEST_AGE,
        debug_mode = True,
    )
    total = len(result.curated) + len(result.serendipity)
    print(f"  CF 하이브리드: {result.is_hybrid} | 반환 총 {total}건")

    # ── 6. 결과 출력 ────────────────────────────────────────────
    divider(f"결과 | 취향 매칭 ({len(result.curated)}건)")
    print_events(result.curated, show_breakdown=True)

    divider(f"결과 | 의외성 ({len(result.serendipity)}건)")
    if result.serendipity:
        print_events(result.serendipity, show_breakdown=True)
    else:
        print("  (의외성 없음 — 미경험 장르 + 무드 일치 조건 미충족)")

    divider()
    print(f"  테스트 완료 ✅  총 {total}건 반환")
    print("─" * 60)


if __name__ == "__main__":
    main()