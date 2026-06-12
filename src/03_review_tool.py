import pandas as pd
import re
import unicodedata
from difflib import SequenceMatcher
import warnings
warnings.filterwarnings('ignore')

# =========================================================================
# [설정]
# =========================================================================
INPUT_CSV  = "merged_events.csv"
OUTPUT_CSV = "review_required.csv"

SIMILARITY_THRESHOLD = 0.85  # 유사도 임계값

# =========================================================================
# [함수 정의]
# =========================================================================
def normalize_title(title):
    """
    제목 정규화
    - 전각문자 → 반각 (＃→#, ａ→a 등)
    - 앞의 [기관명] 제거
    - 뒤의 [지역명] 제거
    - 공백 정규화
    """
    if pd.isna(title):
        return ''
    # 전각 → 반각
    title = unicodedata.normalize('NFKC', str(title))
    # 앞의 [기관명] 제거
    title = re.sub(r'^\[.*?\]\s*', '', title)
    # 뒤의 [지역명] 제거 (예: [서울], [부산])
    title = re.sub(r'\s*\[.*?\]\s*$', '', title)
    # 공백 정규화
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def similarity(a, b):
    """두 문자열 유사도 계산 (0~1)"""
    return SequenceMatcher(None, a, b).ratio()


# =========================================================================
# STEP 1. 데이터 로드
# =========================================================================
print("\n📂 [STEP 1] 데이터 로드")
for enc in ['utf-8-sig', 'cp949', 'utf-8']:
    try:
        df = pd.read_csv(INPUT_CSV, encoding=enc)
        print(f"  로드 완료: {len(df)}건")
        break
    except Exception:
        continue


# =========================================================================
# STEP 2. 제목 정규화
# =========================================================================
print("\n🔧 [STEP 2] 제목 정규화")
df['정규화제목'] = df['제목'].apply(normalize_title)

# 출처 분리
seoul_df = df[df['출처'] == '서울'].copy().reset_index(drop=True)
kopis_df = df[df['출처'] == 'KOPIS'].copy().reset_index(drop=True)
print(f"  서울: {len(seoul_df)}건 / KOPIS: {len(kopis_df)}건")


# =========================================================================
# STEP 3. 중복 의심 추출 (장르 동일한 것만 비교)
# =========================================================================
print("\n🔍 [STEP 3] 중복 의심 추출")

# 비교 대상 장르 (서울-KOPIS 공통 장르만)
COMPARE_GENRES = {
    '클래식 및 독주/독창회', '콘서트', '연극',
    '뮤지컬/오페라', '무용', '국악', '기타'
}

candidates = []

seoul_compare = seoul_df[seoul_df['장르'].isin(COMPARE_GENRES)]
kopis_compare = kopis_df[kopis_df['장르'].isin(COMPARE_GENRES)]

print(f"  비교 대상: 서울 {len(seoul_compare)}건 × KOPIS {len(kopis_compare)}건")

for _, s_row in seoul_compare.iterrows():
    s_title  = s_row['정규화제목']
    s_date   = s_row['시작일']
    s_genre  = s_row['장르']

    # 같은 장르 + 같은 시작일인 KOPIS 행만 비교
    kopis_filtered = kopis_compare[
        (kopis_compare['장르']  == s_genre) &
        (kopis_compare['시작일'] == s_date)
    ]

    for _, k_row in kopis_filtered.iterrows():
        k_title = k_row['정규화제목']

        # ── 정확 매칭
        if s_title == k_title:
            candidates.append({
                '매칭유형':      '정확',
                '유사도':        1.0,
                '서울_공연ID':   s_row['공연ID'],
                '서울_제목':     s_row['제목'],
                '서울_장르':     s_row['장르'],
                '서울_시작일':   s_row['시작일'],
                '서울_장소':     s_row['장소'],
                'KOPIS_공연ID':  k_row['공연ID'],
                'KOPIS_제목':    k_row['제목'],
                'KOPIS_장르':    k_row['장르'],
                'KOPIS_시작일':  k_row['시작일'],
                'KOPIS_장소':    k_row['장소'],
                '판단':          '',   # 검수자 입력: 중복 / 별개
            })
            continue

        # ── 유사도 매칭
        sim = similarity(s_title, k_title)
        if sim >= SIMILARITY_THRESHOLD:
            candidates.append({
                '매칭유형':      '유사도',
                '유사도':        round(sim, 4),
                '서울_공연ID':   s_row['공연ID'],
                '서울_제목':     s_row['제목'],
                '서울_장르':     s_row['장르'],
                '서울_시작일':   s_row['시작일'],
                '서울_장소':     s_row['장소'],
                'KOPIS_공연ID':  k_row['공연ID'],
                'KOPIS_제목':    k_row['제목'],
                'KOPIS_장르':    k_row['장르'],
                'KOPIS_시작일':  k_row['시작일'],
                'KOPIS_장소':    k_row['장소'],
                '판단':          '',
            })

print(f"  중복 의심 추출 완료: {len(candidates)}건")
print(f"    - 정확 매칭: {sum(1 for c in candidates if c['매칭유형'] == '정확')}건")
print(f"    - 유사도 매칭: {sum(1 for c in candidates if c['매칭유형'] == '유사도')}건")


# =========================================================================
# STEP 4. 결과 저장
# =========================================================================
print("\n💾 [STEP 4] 결과 저장")

if candidates:
    result_df = pd.DataFrame(candidates)
    # 유사도 높은 순 정렬
    result_df = result_df.sort_values('유사도', ascending=False).reset_index(drop=True)
    result_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"  저장 완료: {OUTPUT_CSV}")
    print(f"\n  ※ '판단' 컬럼에 중복 또는 별개 를 입력 후 apply_review.py 실행")
else:
    print("  중복 의심 행사 없음. 파일 미생성")

print("\n✅ review_tool.py 완료")