# ARBIT-AI 🎭
> 서울 문화행사 취향 기반 추천 시스템

유저의 취향(장르, 무드, 소분류)을 분석하여 서울 문화행사를 개인화 추천하는 AI 파이프라인입니다.

---

## 📌 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 데이터 출처 | 서울열린데이터광장, KOPIS 공연예술통합전산망 |
| 추천 방식 | 콘텐츠 기반 필터링 (CBF) + 협업 필터링 (CF) 하이브리드 설계 |
| 현재 상태 | CBF 단독 운영 (CF는 유저 로그 조건 충족 시 자동 전환) |
| 추천 결과 | 취향 매칭 7건 + 의외성 3건 = 최대 10건 |

---

## 🗂️ 디렉토리 구조

```
ARBIT-AI/
├── .env                          # 환경 변수 (API 키, DB 접속 정보)
├── .gitignore
├── requirements.txt
├── test_csv.py                   # CSV 기반 파이프라인 테스트 실행 파일
│
├── data/
│   ├── 01_raw/                   # 외부 API 수집 원본
│   ├── 02_intermediate/          # 병합·분류 중간 산출물
│   ├── 03_final/                 # 최종 데이터 (events_with_mood.csv)
│   └── extras/                   # 수동 작성 데이터
│
├── models/
│   ├── classifiers_k1/           # 장르/소분류 분류기 모델
│   └── recommendation/           # 추천 시스템 가중치·행렬 파일
│
└── src/
    ├── 01_fetch_kopis.py         # KOPIS API 수집
    ├── 01_fetch_seoul.py         # 서울열린데이터광장 API 수집
    ├── 02_merge_events.py        # 데이터 병합
    ├── 03_review_tool.py         # 수동 검수 도구
    ├── 04_apply_review.py        # 검수 결과 반영
    ├── 05_subgenre_classification.py  # 소분류 분류
    ├── 06_verify_mood_rules.py   # 무드 규칙 검증
    │
    └── recommendation/           # 추천 엔진 패키지
        ├── __init__.py
        ├── core.py               # 긴급도·콘텐츠 점수 계산
        ├── user_profile.py       # 온보딩 샘플링·유저 프로필 빌드
        ├── cf_utils.py           # 협업 필터링 행렬 연산
        ├── schemas.py            # FastAPI 입출력 스키마 (Pydantic v2)
        └── run_recommend.py      # 추천 파이프라인 실행 진입점
```

---

## ⚙️ 추천 파이프라인

### 스코어링 가중치

```
최종 점수 = 무드(0.35) + 장르(0.30) + 긴급도(0.20) + 소분류(0.15)
```

### 긴급도 계산

```
긴급도 = max(0, 1 - 남은일수 / 기준일수)

전시/미술, 교육/체험 → 기준일 180일
그 외 장르            → 기준일 90일
```

### CF 자동 전환 조건

현재는 CBF 단독 운영이며, 아래 조건 충족 시 자동으로 하이브리드 전환됩니다.

```python
유저 수   >= 500명
행사 수   >= 200건
행렬 밀도 >= 5%

# 전환 후 가중치
최종 점수 = CBF × 0.6 + CF × 0.4
```

### 5단계 파이프라인

```
1. filter_by_age      연령 하드 필터 (게스트 → 기본값 15세 적용)
        ↓
2. sample_onboarding  장르별 균등 샘플링 20건
        ↓
3. build_user_profile 선택 행사 → 장르/소분류/무드 취향 프로필 생성
        ↓
4. content_score      유저 프로필 × 전체 행사 적합도 계산
        ↓
5. recommend          취향 매칭 7건 + 의외성 3건 반환
```

---

## 📊 데이터 파이프라인

```
01_fetch_kopis.py       KOPIS API 수집
01_fetch_seoul.py       서울열린데이터광장 API 수집
        ↓
02_merge_events.py      두 출처 데이터 병합
        ↓
03_review_tool.py       수동 검수 도구
04_apply_review.py      검수 결과 반영
        ↓
05_subgenre_classification.py   소분류 자동 분류
        ↓
06_verify_mood_rules.py         무드 규칙 검증
        ↓
data/03_final/events_with_mood.csv   최종 완성 데이터
```

### 라벨 신뢰도 (reliability)

| 등급 | 출처 | 샘플링 가중치 |
|------|------|--------------|
| BEST | KOPIS 직접 매핑 | 3.0 |
| HIGH | 규칙+분류기 일치 / 분류기+임베딩 일치 | 2.0 |
| MID  | 분류기 선택 | 1.0 |
| LOW  | 분류기 기본값 | 제외 |

---

## 🚀 설치 및 실행

### 패키지 설치

```bash
pip install -r requirements.txt
```

### CSV 기반 파이프라인 테스트

```bash
python test_csv.py
```

`test_csv.py` 상단에서 아래 값을 조정할 수 있습니다.

```python
CSV_PATH = ROOT / "data" / "03_final" / "events_with_mood.csv"  # CSV 경로
TEST_AGE  = 25   # 테스트 유저 연령 (None → 게스트)
SELECT_N  = 7    # 온보딩 20건 중 선택 시뮬레이션 건수 (최소 5 이상)
```

### 실행 결과 예시

```
STEP 1 | 온보딩 샘플링 (20건)
  샘플 결과: 20건 | 장르 분포: 클래식(5), 뮤지컬(3), 콘서트(2) ...

STEP 2 | 유저 선택 시뮬레이션 (7건 / 20건 중)
  ✓ [PF292027] 금호영재 콘서트, 조승언 피아노 독주회 (클래식 및 독주/독창회)
  ...

STEP 3 | 유저 프로필 빌드
  genre   : 클래식 및 독주/독창회(0.29), 교육/체험(0.29), 콘서트(0.14)
  mood    : 힐링/감성(0.43), 감동/웅장(0.21), 학술/사색적(0.14)

STEP 4 | 추천 실행 (최대 10건)
  CF 하이브리드: False | 반환 총 10건

결과 | 취향 매칭 (7건)
  [se124] 강보리 첼로 독주회 | 총:0.4411 장르:0.286 무드:0.321 긴급도:1.000
  ...

결과 | 의외성 (3건)
  [se108] 서리풀 아마추어 남성 성악 콩쿠르 | 총:0.3500
  ...
```

---

## 📋 유저 로그 수집 전략

서비스 런칭 후 아래 행동 데이터를 수집하여 CF 전환에 활용합니다.

| 행동 | 가중치 |
|------|--------|
| 북마크 | +1.0 |
| 예매링크 클릭 | +0.9 |
| 온보딩 선택 | +0.8 |
| 상세 페이지 진입 | +0.4 |
| 15초 이상 체류 | +0.3 |
| 북마크 취소 | -0.5 |
| 추천 무시 | -0.1 |

---

## 🛠️ 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| 데이터 처리 | pandas, numpy |
| API 서버 | FastAPI (연동 예정) |
| 데이터 검증 | Pydantic v2 |
| 협업 필터링 | scipy (sparse matrix) |