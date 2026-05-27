import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
INPUT_CSV   = "seoul_cultural_events.csv"           # 원본 데이터
OUTPUT_CSV  = "seoul_events_preprocessed.csv"       # 정제된 중간 데이터

# 연령 분류용 규칙 상수
AGE_RULES_PRIORITY = ["7세 이상", "8세 이상", "9세 이상", "10세 이상", "11세 이상", "12세 이상", "13세 이상", "14세 이상", "15세 이상", "초등학생 이상", "중학생 이상", "청소년 이상"]
AGE_TARGET_RULES = {
    "태그 없음": ["전체이용가", "전체관람가", "전 연령", "전연령", "누구나", "시민 누구나", "모든 시민", "연령 제한 없음"],
    "청소년 제외": ["19세 이상", "성인 전용", "청소년 관람불가", "청소년 입장불가", "미성년자 입장불가", "성인 대상", "성인만", "청년"],
    "아동/가족 제외": AGE_RULES_PRIORITY + ["학생 대상", "학생 및 성인"],
    "일반 성인 제외": ["유아", "영유아", "아동", "청소년 프로그램", "키즈", "보호자 동반", "어린이 전용"],
}

# ──────────────────────────────────────────────
# 핵심 로직
# ──────────────────────────────────────────────
def build_text_for_age(row):
    cols = ["이용대상", "테마분류", "공연/행사명", "분류", "프로그램소개", "프로그램소개_크롤링", "기타내용"]
    return " ".join(str(row.get(c, "")).strip() for c in cols if str(row.get(c, "")).strip() not in ("", "nan"))

def predict_age_label(text):
    for rule in AGE_RULES_PRIORITY:
        if rule in text: return "아동/가족 제외"
    scores = {label: sum(1 for kw in kws if kw in text) for label, kws in AGE_TARGET_RULES.items()}
    scores = {k: v for k, v in scores.items() if v > 0}
    return max(scores, key=scores.get) if scores else "태그 없음"

def main():
    print("🧹 [STEP 1] 데이터 전처리를 시작합니다...")
    try:
        raw = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"❌ 원본 파일을 찾을 수 없습니다: {INPUT_CSV}")
        return

    # 연령 레이블 생성
    raw["age_label"] = raw.apply(lambda r: predict_age_label(build_text_for_age(r)), axis=1)
    
    # 추천에 필요한 핵심 컬럼만 추출 및 정제
    df = pd.DataFrame({
        "event_id": range(len(raw)),
        "title": raw["공연/행사명"].str.strip(),
        "genre": raw["분류"].str.strip(),
        "district": raw["자치구"].str.strip(),
        "is_free": raw["유무료"].str.strip() == "무료",
        "start_date": pd.to_datetime(raw["시작일"], errors="coerce").dt.date,
        "end_date": pd.to_datetime(raw["종료일"], errors="coerce").dt.date,
        "description": raw["프로그램소개_크롤링"].fillna("").str.strip(),
        "age_label": raw["age_label"],
    })

    # 날짜 없는 데이터 제거 및 인덱스 초기화
    df = df.dropna(subset=["start_date", "end_date"]).reset_index(drop=True)
    
    # 정제된 데이터 저장
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"✅ 전처리 완료! 총 {len(df)}건의 데이터가 저장되었습니다: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()