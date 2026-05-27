import pandas as pd
from datetime import date
from collections import Counter

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
INPUT_CSV    = "events_with_mood.csv"
TODAY        = date.today()
SAMPLE_SIZE  = 10   # 랜덤으로 보여줄 행사 수

# [수정] 장르 다양성에 따라 자동 조정되는 가중치
# - 장르 1~2개 집중: 장르 점수가 의미 있으므로 무드와 균형 유지
# - 장르 3개 이상 분산: 장르 점수가 희석되므로 무드 비중을 높여 보정
WEIGHTS_FOCUSED   = {"genre": 0.40, "mood": 0.45, "urgency": 0.15}
WEIGHTS_DISPERSED = {"genre": 0.30, "mood": 0.55, "urgency": 0.15}

GENRE_MAP = {
    "전시/미술": ["전시/미술"], "연극": ["연극"], "뮤지컬/오페라": ["뮤지컬/오페라"],
    "클래식 및 독주/독창회": ["클래식", "독주/독창회"], "콘서트": ["콘서트"],
    "국악": ["국악"], "무용": ["무용"], "교육/체험": ["교육/체험"], "영화": ["영화"],
    "축제": ["축제-문화/예술", "축제-전통/역사", "축제-기타", "축제-시민화합", "축제-관광/체육", "축제-자연/경관"]
}


# ──────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────
def load_data():
    df = pd.read_csv(INPUT_CSV)
    df["start_date"] = pd.to_datetime(df["start_date"]).dt.date
    df["end_date"]   = pd.to_datetime(df["end_date"]).dt.date
    df["mood_tags"]  = df["mood_tags"].apply(
        lambda x: str(x).split(",") if pd.notnull(x) else ["힐링/감성"]
    )

    def compute_status(r):
        if r["end_date"] < TODAY:                     return "종료"
        if r["start_date"] > TODAY:                   return "예정"
        if (r["end_date"] - TODAY).days <= 7:         return "마감임박"
        return "진행중"

    df["status"]    = df.apply(compute_status, axis=1)
    df["days_left"] = df.apply(lambda r: max(0, (r["end_date"] - TODAY).days), axis=1)
    return df[df["status"] != "종료"].reset_index(drop=True)


# ──────────────────────────────────────────────
# 랜덤 10개 출력 및 4~5개 선택
# ──────────────────────────────────────────────
def select_seed_events(df):
    while True:
        # 랜덤 10개 샘플링
        sample_df = df.sample(n=min(SAMPLE_SIZE, len(df)), random_state=None).reset_index(drop=True)

        print(f"\n{'─'*65}")
        print(f"  아래 {SAMPLE_SIZE}개의 행사 중 관심 있는 항목을 4~5개 선택해주세요.")
        print(f"{'─'*65}\n")

        for i, row in sample_df.iterrows():
            free   = "무료" if row["is_free"] else "유료"
            moods  = ", ".join(row["mood_tags"])
            print(f"  {i+1:>2}. [{row['status']}] {row['title'][:35]}")
            print(f"      장르: {row['genre']:<15} | 지역: {row['district']:<4} | {free}")
            print(f"      무드: {moods}")
            print(f"      기간: ~{row['end_date']} (D-{row['days_left']})\n")

        print("  r. 목록 새로고침 (다른 행사 보기)")
        raw = input("\n▶ 번호 입력 (띄어쓰기 구분, 예: 1 3 5 7): ").strip()

        # 새로고침
        if raw.lower() == "r":
            continue

        nums = list(dict.fromkeys(
            int(t) for t in raw.split() if t.isdigit() and 1 <= int(t) <= len(sample_df)
        ))

        if 4 <= len(nums) <= 5:
            selected = sample_df.iloc[[n - 1 for n in nums]].reset_index(drop=True)
            print(f"\n✅ 선택된 행사 {len(selected)}건:")
            for _, row in selected.iterrows():
                print(f"   - [{row['genre']}] {row['title'][:40]}")
                print(f"     무드: {', '.join(row['mood_tags'])} | 연령: {row['age_label']}")
            return selected

        print(f"\n  ⚠ 4~5개를 선택해야 합니다. (현재 {len(nums)}개 선택)")


# ──────────────────────────────────────────────
# 선택 행사 → 취향 프로필 자동 추출
# ──────────────────────────────────────────────
def extract_preference_profile(selected_df):
    """
    선택한 행사에서 장르/무드/연령 취향을 자동 추출.

    - 장르 가중치: 선택 행사 중 각 장르의 비율
    - 무드 가중치: 선택 행사 전체 무드 태그 빈도의 비율
    - 허용 연령:   선택 행사에 등장한 age_label을 그대로 허용
    """
    # 장르 빈도
    genre_counter = Counter(selected_df["genre"].tolist())
    total_genre   = sum(genre_counter.values())
    genre_weights = {g: c / total_genre for g, c in genre_counter.items()}

    # 무드 빈도
    mood_counter = Counter(
        mood for tags in selected_df["mood_tags"] for mood in tags
    )
    total_mood   = sum(mood_counter.values())
    mood_weights = {m: c / total_mood for m, c in mood_counter.items()}

    # 허용 연령 레이블
    allowed_ages = set(selected_df["age_label"].tolist())

    print(f"\n📊 자동 추출된 취향 프로필")
    print(f"   장르: {', '.join(f'{g}({v:.0%})' for g, v in genre_weights.items())}")
    print(f"   무드: {', '.join(f'{m}({v:.0%})' for m, v in mood_weights.items())}")
    print(f"   연령: {', '.join(allowed_ages)}")

    return genre_weights, mood_weights, allowed_ages


# ──────────────────────────────────────────────
# 스코어링 (벡터 연산 + 동적 가중치)
# ──────────────────────────────────────────────
def score_all(df, genre_weights, mood_weights):
    df = df.copy()

    # ── [수정] 장르 다양성에 따라 가중치 자동 결정
    # 장르가 3개 이상으로 분산 → 장르 점수가 희석되므로 무드 비중 높임
    # 장르가 1~2개로 집중  → 장르 점수가 의미 있으므로 균형 유지
    genre_diversity = len(genre_weights)
    weights = WEIGHTS_DISPERSED if genre_diversity >= 3 else WEIGHTS_FOCUSED
    print(f"\n⚙ 적용된 가중치 — "
          f"장르: {weights['genre']:.0%} / "
          f"무드: {weights['mood']:.0%} / "
          f"긴급도: {weights['urgency']:.0%} "
          f"({'분산형' if genre_diversity >= 3 else '집중형'}, 선택 장르 {genre_diversity}개)")

    # ── 장르 점수: 선택 행사 내 해당 장르 비율
    df["genre_score"] = df["genre"].apply(
        lambda g: genre_weights.get(g, 0.0)
    )

    # ── 무드 점수: 행사 무드 태그와 취향 무드 가중치 합산 (최대 1.0)
    df["mood_score"] = df["mood_tags"].apply(
        lambda tags: min(sum(mood_weights.get(t, 0.0) for t in tags), 1.0)
    )

    # ── 긴급도 점수
    df["urgency"] = 0.0
    active_mask       = df["status"].isin(["진행중", "마감임박"])
    imminent_mask     = active_mask & (df["days_left"] <= 7)
    not_imminent_mask = active_mask & (df["days_left"] > 7)

    df.loc[imminent_mask, "urgency"] = 1.0
    df.loc[not_imminent_mask, "urgency"] = (
        1.0 - df.loc[not_imminent_mask, "days_left"] / 90
    ).clip(lower=0.0)

    # ── 최종 점수 (동적 가중치 적용)
    df["score"] = (
        weights["genre"]   * df["genre_score"] +
        weights["mood"]    * df["mood_score"]  +
        weights["urgency"] * df["urgency"]
    ).round(4)

    # ── [추가] 정규화 — 후보 중 최고점을 100%로 기준 삼아 상대적 매칭률 계산
    # 공식: (현재 점수 - 최솟값) / (최댓값 - 최솟값) * 100
    max_score   = df["score"].max()
    min_score   = df["score"].min()
    score_range = max_score - min_score

    if score_range > 0:
        df["match_pct"] = ((df["score"] - min_score) / score_range * 100).round(1)
    else:
        df["match_pct"] = 100.0  # 모든 점수가 동일하면 전부 100%

    df["genre_score"] = df["genre_score"].round(2)
    df["mood_score"]  = df["mood_score"].round(2)
    df["urgency"]     = df["urgency"].round(2)

    return df.sort_values("score", ascending=False).reset_index(drop=True)


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    print("="*60 + "\n🎯 스마트 문화행사 추천 시스템\n" + "="*60)
    try:
        df = load_data()
    except FileNotFoundError:
        print("\n❌ 에러: 'events_with_mood.csv' 파일이 없습니다. 1_llm_mood_extractor.py를 먼저 실행하세요.")
        return

    # 1. 랜덤 10개에서 4~5개 선택
    selected_df = select_seed_events(df)

    # 2. 장르/무드/연령 취향 자동 추출
    genre_weights, mood_weights, allowed_ages = extract_preference_profile(selected_df)

    # 3. 연령 필터 + 선택 행사 제외
    selected_ids  = set(selected_df["event_id"].tolist())
    df_candidates = df[
        df["age_label"].isin(allowed_ages) &
        ~df["event_id"].isin(selected_ids)
    ].reset_index(drop=True)

    print(f"\n→ 추천 후보: {len(df_candidates)}건")

    # 4. 스코어링
    scored = score_all(df_candidates, genre_weights, mood_weights)

    # 5. 결과 출력 (상위 10개)
    print("\n" + "★"*60)
    print(f" 맞춤형 추천 결과 (총 {len(scored)}건 중 상위 10건)")
    print("★"*60)

    for i, row in scored.head(10).iterrows():
        badge = f"[{row['status']}]"
        src   = "[LLM]" if row.get("mood_source") == "llm" else ""
        print(f"\n{i+1}. {badge} {row['title'][:40]}")
        print(f"   ▫ 장르/지역 : {row['genre']} | {row['district']} | {'무료' if row['is_free'] else '유료'}")
        print(f"   ▫ 일정/연령 : ~{row['end_date']} (D-{row['days_left']}) | {row['age_label']}")
        print(f"   ▫ 태그 {src}  : {', '.join(row['mood_tags'])}")
        print(f"   ▫ 매칭률    : {row['match_pct']:.1f}% (장르 {row['genre_score']}, 무드 {row['mood_score']}, 긴급도 {row['urgency']})")

if __name__ == "__main__":
    main()