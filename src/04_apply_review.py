import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# =========================================================================
# [설정]
# =========================================================================
MERGED_CSV  = "merged_events.csv"
REVIEW_CSV  = "review_required.csv"
OUTPUT_CSV  = "reviewed_events.csv"

# =========================================================================
# STEP 1. 데이터 로드
# =========================================================================
print("\n📂 [STEP 1] 데이터 로드")

def load_csv(path, name):
    for enc in ['utf-8-sig', 'cp949', 'utf-8']:
        try:
            df = pd.read_csv(path, encoding=enc)
            print(f"  [{name}] 로드 완료: {len(df)}건")
            return df
        except Exception:
            continue
    raise ValueError(f"CSV 로드 실패: {path}")

merged = load_csv(MERGED_CSV, 'merged_events')
review = load_csv(REVIEW_CSV, 'review_required')


# =========================================================================
# STEP 2. 검수 결과 검증
# =========================================================================
print("\n🔍 [STEP 2] 검수 결과 검증")

# 판단 컬럼 공백 제거
review['판단'] = review['판단'].fillna('').str.strip()

total      = len(review)
duplicates = review[review['판단'] == '중복']
separate   = review[review['판단'] == '별개']
empty      = review[review['판단'] == '']

print(f"  전체 검수 항목: {total}건")
print(f"    - 중복:   {len(duplicates)}건")
print(f"    - 별개:   {len(separate)}건")
print(f"    - 미입력: {len(empty)}건")

# 미입력 항목 경고
if len(empty) > 0:
    print(f"\n  ⚠️ 미입력 항목 {len(empty)}건 발견 → 별개로 처리합니다.")
    print("  미입력 목록:")
    for _, row in empty.iterrows():
        print(f"    서울: {row['서울_제목']} | KOPIS: {row['KOPIS_제목']}")


# =========================================================================
# STEP 3. 중복 제거 (서울 행 제거, KOPIS 유지)
# =========================================================================
print("\n🗑️  [STEP 3] 중복 제거")

# 중복으로 판단된 서울 공연ID 수집
remove_ids = set(duplicates['서울_공연ID'].tolist())
print(f"  제거 대상 서울 공연ID: {len(remove_ids)}건")
for pid in remove_ids:
    title = merged[merged['공연ID'] == pid]['제목'].values
    print(f"    {pid}: {title[0] if len(title) > 0 else '알수없음'}")

# 중복 행 제거
before_count = len(merged)
reviewed = merged[~merged['공연ID'].isin(remove_ids)].copy()
reviewed = reviewed.reset_index(drop=True)
after_count = len(reviewed)

print(f"\n  제거 전: {before_count}건 → 제거 후: {after_count}건 (제거: {before_count - after_count}건)")


# =========================================================================
# STEP 4. 결과 저장 및 요약
# =========================================================================
print("\n💾 [STEP 4] 결과 저장")

reviewed.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
print(f"  저장 완료: {OUTPUT_CSV}")

print("\n📊 [요약]")
print(f"  최종 데이터:  {len(reviewed)}건")
print(f"  서울:         {(reviewed['출처'] == '서울').sum()}건")
print(f"  KOPIS:        {(reviewed['출처'] == 'KOPIS').sum()}건")
print(f"  중복 제거:    {before_count - after_count}건")

print("\n  장르 분포:")
print(reviewed['장르'].value_counts().to_string())

print("\n✅ apply_review.py 완료")
print(f"   다음 단계: 0_data_processing.py 실행 (입력: {OUTPUT_CSV})")