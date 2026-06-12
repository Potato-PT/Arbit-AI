import pandas as pd
import re
import warnings
warnings.filterwarnings('ignore')

# =========================================================================
# [설정]
# =========================================================================
SEOUL_CSV   = "seoul_raw.csv"
KOPIS_CSV   = "kopis_raw.csv"
OUTPUT_CSV  = "merged_events.csv"

# =========================================================================
# [장르 매핑 테이블]
# =========================================================================
SEOUL_GENRE_MAP = {
    '클래식':        '클래식 및 독주/독창회',
    '독주/독창회':   '클래식 및 독주/독창회',
    '콘서트':        '콘서트',
    '무용':          '무용',
    '연극':          '연극',
    '뮤지컬/오페라': '뮤지컬/오페라',
    '국악':          '국악',
    '영화':          '영화',
    '교육/체험':     '교육/체험',
    '전시/미술':     '전시/미술',
    '기타':          '기타',
    '축제-문화/예술': '축제(통합)',
    '축제-전통/역사': '축제(통합)',
    '축제-기타':      '축제(통합)',
    '축제-시민화합':  '축제(통합)',
    '축제-관광/체육': '축제(통합)',
    '축제-자연/경관': '축제(통합)',
}

KOPIS_GENRE_MAP = {
    '서양음악(클래식)':    '클래식 및 독주/독창회',
    '대중음악':            '콘서트',
    '연극':                '연극',
    '뮤지컬':              '뮤지컬/오페라',
    '오페라':              '뮤지컬/오페라',
    '무용(서양/한국무용)': '무용',
    '한국음악(국악)':      '국악',
    '아동가족':            '연극',
    '서커스/마술':         '기타',
    '복합':                '기타',
}

# =========================================================================
# [연령 분류 규칙]
# =========================================================================
ADULT_KW    = ['성인', '어른', '학부모', '교사', '보호자']
CHILDREN_KW = ['어린이', '아동', '유아', '영유아', '키즈']

PRIORITY_PATTERNS = [
    r'(?<!\d)[7-9]세\s*이상',
    r'(?<!\d)1[0-8]세\s*이상',
    r'만\s*[7-9]세',
    r'만\s*1[0-8]세',
    r'초등학생',
    r'초등학교',
    r'초등\s*[1-6]학년',
    r'초등\s*이상',
    r'중학생.{0,10}이상',
    r'중학생이상',
    r'청소년.{0,10}이상',
    r'고등학생',
    r'고등학교\s*단체',
    r'중ㆍ고등',
    r'중,\s*고등',
    r'중~고등',
    r'미취학아동\s*입장\s*불가',
    r'취학아동\s*이상',
    r'학생\s*대상',
    r'학생\s*및\s*성인',
]

AGE_RULES = {
    '전체이용가': [
        '누구나', '전체관람가', '전체이용가', '전 연령', '전연령',
        '모든 시민', '시민 누구나', '연령 제한 없음', '제한 없음',
        '전체관람', '전체 관람가능', '전체 관람가', '누구나 관람',
        '일반 누구나', '현장 자유 관람',
    ],
    '성인 only': [
        '19세 이상', '만 19세', '성인 전용', '성인만', '성인 대상',
        '청소년 관람불가', '청소년 입장불가', '미성년자 입장불가',
        '일반 성인', '성인 누구나', '성인 학습자',
        '청년', '중장년', '시니어',
    ],
    '미성년자 only': [
        '6세 이상', '만 6세',
        '12개월 이상', '20개월 이상', '24개월 이상',
        '30개월 이상', '36개월 이상', '48개월 이상',
        '만 2세', '만 3세', '만 4세', '만 5세', '만4세',
        '유아', '영유아', '어린이', '아동', '키즈',
        '어린이 전용', '어린이집', '유치원',
        '청소년 프로그램', '어린이,청소년', '어린이를 동반', '돌봄',
    ],
}

# =========================================================================
# [함수 정의]
# =========================================================================
def load_csv(path, name):
    for enc in ['utf-8-sig', 'cp949', 'utf-8']:
        try:
            df = pd.read_csv(path, encoding=enc)
            print(f"  [{name}] 로드 완료: {len(df)}건")
            return df
        except Exception:
            continue
    raise ValueError(f"CSV 로드 실패: {path}")


def unify_date(value):
    """날짜 형식 → YYYY-MM-DD 통일"""
    if pd.isna(value):
        return None
    value = str(value).strip()
    # 서울: "2026-10-15 00:00:00.0"
    # KOPIS: "2026.06.13"
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d', '%Y.%m.%d'):
        try:
            return pd.to_datetime(value, format=fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    try:
        return pd.to_datetime(value).strftime('%Y-%m-%d')
    except Exception:
        return None


def extract_district(address):
    """주소에서 자치구 추출"""
    if pd.isna(address):
        return None
    match = re.search(r'[가-힣]+(?:구|군)', str(address))
    return match.group() if match else None


def infer_is_free(price):
    """KOPIS 티켓가격에서 유무료 유추 (가격 정보 없으면 유료로 처리)"""
    if pd.isna(price) or str(price).strip() == '':
        return False
    return '무료' in str(price)


def build_age_text(row, cols):
    """연령 분류용 텍스트 조합"""
    return ' '.join(
        str(row.get(c, '')).strip()
        for c in cols
        if str(row.get(c, '')).strip() not in ('', 'nan')
    )


def predict_age_label(text):
    """연령 레이블 분류"""
    # [1단계] PRIORITY → 학생/성인
    for pattern in PRIORITY_PATTERNS:
        if re.search(pattern, text):
            return '학생/성인'

    # [2단계] 성인 + 어린이 혼합 → 전체이용가
    has_adult    = any(kw in text for kw in ADULT_KW)
    has_children = any(kw in text for kw in CHILDREN_KW)
    if has_adult and has_children:
        return '전체이용가'

    # [3단계] 키워드 점수 계산
    scores = {
        label: sum(1 for kw in kws if kw in text)
        for label, kws in AGE_RULES.items()
    }
    scores = {k: v for k, v in scores.items() if v > 0}
    return max(scores, key=scores.get) if scores else '전체이용가'


# =========================================================================
# STEP 1. 데이터 로드
# =========================================================================
print("\n📂 [STEP 1] 데이터 로드")
seoul = load_csv(SEOUL_CSV, '서울')
kopis = load_csv(KOPIS_CSV, 'KOPIS')


# =========================================================================
# STEP 2. 서울 데이터 정제
# =========================================================================
print("\n🔧 [STEP 2] 서울 데이터 정제")

seoul_age_cols = ['이용대상', '분류', '프로그램소개_크롤링']
seoul_processed = pd.DataFrame({
    '공연ID':    [f'se{i}' for i in range(len(seoul))],  # ✅ 서울만 se+n 생성
    '출처':      '서울',
    '제목':      seoul['공연/행사명'].str.strip(),
    '장르':      seoul['분류'].map(SEOUL_GENRE_MAP).fillna('기타'),
    '장르_원본': seoul['분류'].str.strip(),              # ✅ 원본 장르 보존
    '시작일':   seoul['시작일'].apply(unify_date),
    '종료일':   seoul['종료일'].apply(unify_date),
    '장소':     seoul['장소'].str.strip(),
    '주소':     None,
    '자치구':   seoul['자치구'].str.strip(),
    '위도':     pd.to_numeric(seoul['위도'], errors='coerce'),
    '경도':     pd.to_numeric(seoul['경도'], errors='coerce'),
    '관람연령': seoul['이용대상'].str.strip(),
    'age_label': seoul.apply(
        lambda r: predict_age_label(build_age_text(r, seoul_age_cols)), axis=1
    ),
    '티켓가격': seoul['이용요금'].fillna('').str.strip(),
    'is_free':  seoul['유무료'].str.strip() == '무료',
    '대표이미지': seoul['대표이미지'],
    '소개':     seoul['프로그램소개_크롤링'].fillna('').str.strip(),
    '예매링크': seoul['홈페이지주소'],
})
print(f"  서울 정제 완료: {len(seoul_processed)}건")


# =========================================================================
# STEP 3. KOPIS 데이터 정제
# =========================================================================
print("\n🔧 [STEP 3] KOPIS 데이터 정제")

kopis_age_cols = ['관람연령', '장르', '줄거리']
kopis_processed = pd.DataFrame({
    '공연ID':    kopis['공연ID'],                         # ✅ KOPIS 원본 ID 보존 (PF...)
    '출처':      'KOPIS',
    '제목':      kopis['공연명'].str.strip(),
    '장르':      kopis['장르'].map(KOPIS_GENRE_MAP).fillna('기타'),
    '장르_원본': kopis['장르'].str.strip(),              # ✅ 원본 장르 보존
    '시작일':   kopis['공연시작일'].apply(unify_date),
    '종료일':   kopis['공연종료일'].apply(unify_date),
    '장소':     kopis['공연장'].str.strip(),
    '주소':     kopis['주소'],
    '자치구':   kopis['주소'].apply(extract_district),
    '위도':     pd.to_numeric(kopis['위도'], errors='coerce'),
    '경도':     pd.to_numeric(kopis['경도'], errors='coerce'),
    '관람연령': kopis['관람연령'].str.strip(),
    'age_label': kopis.apply(
        lambda r: predict_age_label(build_age_text(r, kopis_age_cols)), axis=1
    ),
    '티켓가격': kopis['티켓가격'].fillna('').str.strip(),
    'is_free':  kopis['티켓가격'].apply(infer_is_free),
    '대표이미지': kopis['포스터'],
    '소개':     kopis['줄거리'].fillna('').str.strip(),
    '예매링크': kopis['예매링크'],
})
print(f"  KOPIS 정제 완료: {len(kopis_processed)}건")


# =========================================================================
# STEP 4. 병합 및 공연ID 생성
# =========================================================================
print("\n🔗 [STEP 4] 병합")

merged = pd.concat([seoul_processed, kopis_processed], ignore_index=True)

# ✅ 티켓가격에 금액(원)이 있으면 is_free = False로 보정
price_has_amount = merged['티켓가격'].str.contains('원', na=False)
before = merged['is_free'].sum()
merged.loc[price_has_amount, 'is_free'] = False
after = merged['is_free'].sum()
corrected = before - after
if corrected > 0:
    print(f"  ⚠️ is_free 보정: {corrected}건 (티켓가격에 금액 있으나 무료로 표기된 케이스)")

print(f"  병합 완료: {len(merged)}건")


# =========================================================================
# STEP 5. 결과 저장 및 요약
# =========================================================================
print("\n💾 [STEP 5] 결과 저장")

# 컬럼 순서 확정
col_order = [
    '공연ID', '출처', '제목', '장르', '장르_원본', '시작일', '종료일',
    '장소', '주소', '자치구', '위도', '경도',
    '관람연령', 'age_label', '티켓가격', 'is_free',
    '대표이미지', '소개', '예매링크',
]
merged = merged[col_order]
merged.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

print(f"  저장 완료: {OUTPUT_CSV}")

print("\n📊 [요약]")
print(f"  총 데이터:   {len(merged)}건")
print(f"  서울:        {(merged['출처'] == '서울').sum()}건")
print(f"  KOPIS:       {(merged['출처'] == 'KOPIS').sum()}건")
print(f"\n  장르 분포:")
print(merged['장르'].value_counts().to_string())
print(f"\n  연령 분포:")
print(merged['age_label'].value_counts().to_string())
print(f"\n  유무료 분포:")
print(merged['is_free'].value_counts().to_string())