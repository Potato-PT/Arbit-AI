# -*- coding: utf-8 -*-
"""
소분류(키워드1) 분류기 - [버그 수정본 + 오분류 패턴 분석 추가]
수정 사항:
  1. [BUG FIX] rule_acc 계산 오류 수정 (list vs Series 비교 문제)
  2. [BUG FIX] synthetic_data.csv 경로 문제 수정 + 에러 메시지 명확화
  3. [추가] 오분류 패턴 분석 (장르 내 vs 장르 간 오분류, 도입 판단)
"""

import os
import pandas as pd
import numpy as np
import torch
import joblib
from sentence_transformers import SentenceTransformer, util
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split
from tqdm import tqdm

# =========================================================
# [설정] 파일 경로 및 하이퍼파라미터
# =========================================================
LABELED_PATH   = "train_set_500.csv"
RAW_PATH       = "culture_events.csv"
EVENTS_PATH    = "reviewed_events.csv"

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SYNTHETIC_PATH = os.path.join(SCRIPT_DIR, "synthetic_data.csv")

CLASSIFIER_DIR = "classifiers_k1/"
OUTPUT_PATH    = "events_with_subgenre.csv"

MIN_TEXT_LEN       = 40
SEMANTIC_THRESHOLD = 0.35
RANDOM_STATE       = 42
VAL_SIZE           = 0.2
LABEL_COL_K1       = "키워드1_소분류"

os.makedirs(CLASSIFIER_DIR, exist_ok=True)

# =========================================================
# [소분류 체계 및 사전 정의]
# =========================================================
SUB_DICT = {
    "전시/미술": {
        "개인전/초대전":  "개인전, 초대전, 작가전 형식의 단독 전시, 개인 작가 미술展",
        "기획/테마 전시": "특정 주제나 시즌으로 기획된 특별전, 기획전시, 그룹전, 테마전, 미디어아트",
        "역사/문화/산업": "박물관 소장품, 유물, 문화재, 고고, 공예, 도자기, 섬유, 박람회, 페어, 산업전",
    },
    "클래식 및 독주/독창회": {
        "관현악/교향곡": "오케스트라, 교향악단, 관현악 연주, 필하모닉, 심포니 공연",
        "기악 독주회":   "피아노, 바이올린, 첼로 독주 리사이틀, 기악 연주회, 독주회",
        "실내악/앙상블": "실내악, 앙상블, 트리오, 콰르텟 등 소규모 합주, 실내악단 공연",
    },
    "교육/체험": {
        "만들기/공방 체험": "공예 만들기, 공방, DIY, 핸드메이드, 원데이클래스, 어린이 체험",
        "도서/독서 연계":   "북토크, 독서 모임, 작가와의 만남, 도서관 연계 프로그램",
        "학술/강연":        "강연, 세미나, 워크숍, 인문학 강좌, 학술 토론, 명사 초청 포럼",
    },
    "축제(통합)": {
        "야외 체험 행사":     "한강, 공원, 봄꽃, 정원, 드론쇼, 야경, 런페스타, 야시장, 불꽃축제",
        "종합 문화 페스티벌": "공연·먹거리·체험이 어우러진 종합 문화예술 축제, 예술제, 페스티벌",
        "체험/참여형 축제":   "시민 참여 축제, 체험 부스, 마켓, 플리마켓, 참여형 행사",
        "기념/역사 축제":     "전통 제례, 역사 기념, 민속 축제, 종교 기념 행사, 문화재 야행",
    },
    "연극": {
        "아동/가족극":      "어린이극, 가족극, 인형극, 영유아 대상 연극",
        "기획/프로젝트극":  "실험극, 프로젝트 공연, 신작 초연, 기획 연극",
        "정통 연극/극단전": "고전 희곡, 정극, 극단 정기 공연, 낭독극, 연극제",
    },
    "콘서트": {
        "재즈/크로스오버":  "재즈 라이브, 크로스오버, 퓨전 장르 콘서트",
        "대중/인디 음악":   "인디밴드, 싱어송라이터, 대중가요, 록, 포크 콘서트",
        "고궁/야외 콘서트": "고궁, 야외무대, 공원, 한강 등에서 열리는 야외 콘서트, 버스킹",
        "성악/팝페라":      "팝페라, 성악 갈라, 소프라노, 테너, 바리톤 독창, 가곡의 밤",
    },
    "국악": {
        "전통 국악":      "가야금, 거문고, 대금, 해금, 산조, 판소리, 소리극, 창극, 민요, 국악 관현악",
        "창작/퓨전 국악": "국악과 다른 장르 융합, 창작 국악, 퓨전 국악 공연",
    },
    "뮤지컬/오페라": {
        "뮤지컬": "대극장 또는 중극장 규모 뮤지컬, 어린이 뮤지컬, 가족 뮤지컬",
        "오페라": "오페라 전막, 미니어처 오페라, 오페라 갈라, 성악극",
    },
    "무용": {
        "발레":          "클래식 발레, 창작 발레, 발레 갈라 공연",
        "현대/창작무용": "컨템포러리 댄스, 실험적 현대무용, 창작무용 공연",
        "전통무용":      "한국 전통무용, 궁중무용, 민속무용, 창작 한국무용, 살풀이",
    },
    "영화": {
        "특별 상영회/페스타":  "상영회, 영화제, 필름 페스타, 특별 기획 상영회, 독립영화제",
        "고전/독립/예술 영화": "고전 명작, 시니어 영화, 독립영화, 예술영화, 배리어프리 영화",
    },
    "기타": {
        "기타": "수문장 교대식, 전통 의식, 장르 불명확한 기타 행사, 드론쇼, 야경 행사",
    },
}

SUB_RULES = {
    "전시/미술": {
        "개인전/초대전":  ["개인전", "초대전", "작가전"],
        "기획/테마 전시": ["특별기획전", "기획전시", "미디어아트 특별전"],
        "역사/문화/산업": ["박물관 소장품", "유물 전시", "고고학", "도자 전시", "산업 박람회", "아트페어"],
    },
    "클래식 및 독주/독창회": {
        "관현악/교향곡": ["오케스트라", "교향악단", "필하모닉", "심포니"],
        "기악 독주회":   ["피아노 독주회", "바이올린 독주", "첼로 독주", "리사이틀"],
        "실내악/앙상블": ["실내악", "콰르텟", "듀오", "트리오", "목관 앙상블"],
    },
    "교육/체험": {
        "만들기/공방 체험": ["공방 체험", "원데이클래스", "어린이 DIY"],
        "도서/독서 연계":   ["북토크", "작가와의 만남", "독서 모임"],
        "학술/강연":        ["인문학 강좌", "학술 세미나", "명사 포럼", "심포지엄"],
    },
    "축제(통합)": {
        "야외 체험 행사":     ["런페스타", "불꽃축제", "드론 라이트쇼"],
        "종합 문화 페스티벌": ["종합 예술제", "프린지 페스티벌"],
        "체험/참여형 축제":   ["시민 플리마켓", "체험 부스 운영"],
        "기념/역사 축제":     ["종묘 대제", "문화재 야행"],
    },
    "연극": {
        "아동/가족극":      ["어린이 인형극", "영유아 가족극", "어린이 연극", "아이들극장"],
        "기획/프로젝트극":  ["실험극 초연", "창작 희곡 낭독"],
        "정통 연극/극단전": ["극단 정기공연", "정극 연극제"],
    },
    "콘서트": {
        "재즈/크로스오버":  ["재즈 라이브", "크로스오버 콘서트"],
        "대중/인디 음악":   ["인디밴드 라이브", "록 페스티벌", "아이돌 콘서트"],
        "고궁/야외 콘서트": ["고궁 음악회", "야외 버스킹", "운현궁", "경복궁", "창덕궁", "덕수궁", "창경궁"],
        "성악/팝페라":      ["팝페라 콘서트", "소프라노 독창회", "테너 리사이틀", "바리톤 독창회"],
    },
    "국악": {
        "전통 국악":      ["정통 산조", "판소리 완창", "종묘제례악", "정악"],
        "창작/퓨전 국악": ["퓨전 국악", "국악 크로스오버", "창작 국악극"],
    },
    "뮤지컬/오페라": {
        "뮤지컬": ["어린이 뮤지컬", "라이선스 뮤지컬", "창작 뮤지컬"],
        "오페라": ["오페라 전막", "오페라 갈라"],
    },
    "무용": {
        "발레":          ["클래식 발레", "낭만 발레"],
        "현대/창작무용": ["컨템포러리 댄스", "실험 무용"],
        "전통무용":      ["궁중무용", "살풀이춤", "전통 민속무용", "한국 전통무용"],
    },
    "영화": {
        "특별 상영회/페스타":  ["영화제 폐막작", "특별 기획 상영", "필름 페스티벌"],
        "고전/독립/예술 영화": ["독립영화 상영", "예술영화 전용관", "고전 명작 상영"],
    },
    "기타": {
        "기타": ["수문장 교대식", "보신각 타종"],
    },
}

RAW_TO_SUB_KEY = {
    "클래식":          "클래식 및 독주/독창회",
    "독주/독창회":     "클래식 및 독주/독창회",
    "전시/미술":       "전시/미술",
    "교육/체험":       "교육/체험",
    "축제-문화/예술":  "축제(통합)",
    "축제-기타":       "축제(통합)",
    "축제-전통/역사":  "축제(통합)",
    "축제-자연/경관":  "축제(통합)",
    "축제-관광/체육":  "축제(통합)",
    "축제-시민화합":   "축제(통합)",
    "연극":            "연극",
    "콘서트":          "콘서트",
    "국악":            "국악",
    "뮤지컬/오페라":   "뮤지컬/오페라",
    "무용":            "무용",
    "영화":            "영화",
    "기타":            "기타",
    "클래식 및 독주/독창회": "클래식 및 독주/독창회",
    "축제(통합)":            "축제(통합)",
    "서양음악(클래식)":    "클래식 및 독주/독창회",
    "대중음악":            "콘서트",
    "뮤지컬":              "뮤지컬/오페라",
    "오페라":              "뮤지컬/오페라",
    "무용(서양/한국무용)": "무용",
    "한국음악(국악)":      "국악",
    "서커스/마술":         "기타",
    "복합":                "기타",
    "아동가족":            "연극",
}

# =========================================================
# ✅ KOPIS 원본 장르 → 소분류 직접 매핑
# 소분류 구분이 명확한 KOPIS 장르만 직접 매핑
# 소분류가 여러 개인 장르(서양음악, 연극, 무용, 국악)는 분류기 사용
# =========================================================
KOPIS_DIRECT_MAP = {
    # 소분류 1개로 명확히 매핑 가능
    "대중음악":    "대중/인디 음악",   # 콘서트 내 → 대중/인디 음악으로 직접
    "뮤지컬":     "뮤지컬",           # 뮤지컬/오페라 → 뮤지컬 확정
    "오페라":     "오페라",           # 뮤지컬/오페라 → 오페라 확정
    "서커스/마술": "기타",             # 기타 → 기타 확정
    "복합":       "기타",             # 기타 → 기타 확정
    "아동가족":   "아동/가족극",       # 연극 → 아동/가족극 확정
    # 아래는 소분류 구분 필요 → 분류기 사용
    # "서양음악(클래식)" → 관현악/교향곡, 기악 독주회, 실내악/앙상블 중 선택
    # "연극"            → 아동/가족극, 기획/프로젝트극, 정통 연극/극단전 중 선택
    # "무용(서양/한국무용)" → 발레, 현대/창작무용, 전통무용 중 선택
    # "한국음악(국악)"  → 전통 국악, 창작/퓨전 국악 중 선택
}

# =========================================================
# [유틸 함수]
# =========================================================
def load_csv(path):
    for enc in ['utf-8-sig', 'cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv(path, encoding=enc)
            print(f"  [로드 완료] {path} ({enc}) — {len(df)}건")
            return df
        except Exception:
            continue
    print(f"  [오류] 파일을 찾을 수 없습니다: {path}")
    return pd.DataFrame()

TEXT_COLS = [
    '분류', '장르', '공연/행사명', '제목',
    '출연자정보', '프로그램소개', '소개',
    '프로그램소개_크롤링', '기타내용',
    '이용대상', '테마분류', '행사시간', '장소'
]

def clean_text_cols(df):
    for col in TEXT_COLS:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip()
        else:
            df[col] = ''
    return df

def build_text(row):
    title  = row.get("제목") or row.get("공연/행사명", "")
    genre  = row.get("장르") or row.get("분류", "")
    desc   = row.get("소개") or row.get("프로그램소개_크롤링") or row.get("프로그램소개", "")
    perf   = row.get("출연자정보", "")
    extra  = row.get("기타내용", "")
    place  = row.get("장소", "")
    return f"{title} {genre} {perf} {desc} {extra} {place}".strip()

def get_genre_key(row):
    raw = row.get("장르") or row.get("분류") or "기타"
    return RAW_TO_SUB_KEY.get(str(raw).strip(), "기타")

def rule_match_scored(text, rules):
    scores = {}
    for cat, kws in rules.items():
        hits = [kw for kw in kws if kw in text]
        if hits:
            scores[cat] = len(hits)
    if not scores:
        return None
    return max(scores, key=scores.get)

def semantic_top(text, names, embs, threshold=SEMANTIC_THRESHOLD):
    t_emb  = model.encode(text, convert_to_tensor=True)
    scores = util.cos_sim(t_emb, embs)[0]
    best   = int(torch.argmax(scores))
    best_score = float(scores[best])
    if best_score < threshold:
        return None, best_score
    return names[best], best_score

def hybrid_classify_k1(row, row_emb, classifier, label_enc):
    key  = get_genre_key(row)
    text = build_text(row)

    # ✅ [0단계] KOPIS 원본 장르 직접 매핑 (소분류 명확한 경우)
    if row.get("출처") == "KOPIS":
        raw_genre = str(row.get("장르_원본", "")).strip()
        if raw_genre in KOPIS_DIRECT_MAP:
            return KOPIS_DIRECT_MAP[raw_genre], "KOPIS 직접 매핑"

    rich = (
        len(row.get("소개", "")) +
        len(row.get("프로그램소개_크롤링", "")) +
        len(row.get("프로그램소개", "")) +
        len(row.get("출연자정보", "")) +
        len(row.get("기타내용", ""))
    ) >= MIN_TEXT_LEN

    sub_info = SUB_EMBS.get(key) or SUB_EMBS["기타"]
    if key not in SUB_EMBS:
        key = "기타"

    rule_result   = rule_match_scored(text, SUB_RULES.get(key, {}))
    valid_subcats = list(SUB_DICT.get(key, {"기타": "기타"}).keys())

    probas = classifier.predict_proba([row_emb])[0]
    best_idx, best_prob = -1, -1.0
    for idx, c_name in enumerate(label_enc.classes_):
        if c_name in valid_subcats and probas[idx] > best_prob:
            best_prob = probas[idx]
            best_idx  = idx
    clf_result = label_enc.classes_[best_idx] if best_idx != -1 else "기타"

    if rule_result and rule_result == clf_result:
        return rule_result, "규칙+분류기 일치"
    if rule_result and not rich:
        return rule_result, "규칙 우선(소개 부족)"
    if rich:
        sem_result, _ = semantic_top(text, sub_info["names"], sub_info["embs"])
        if sem_result and (clf_result == sem_result):
            return clf_result, "분류기+임베딩 일치"
        if rule_result:
            return rule_result, "규칙 우선(소개 충분)"
        return clf_result, "분류기 선택"

    return clf_result, "분류기 기본값"


# =========================================================
# STEP 1. 데이터 로드 및 정보 비대칭 해결
# =========================================================
print("\n📂 [STEP 1] 데이터 로드 및 정보 비대칭 해결")

df_labeled_raw = load_csv(LABELED_PATH)
df_raw         = load_csv(RAW_PATH)
df_events      = load_csv(EVENTS_PATH)

if df_raw.empty:
    print(f"  [경고] {RAW_PATH} 파일이 없어 텍스트 병합을 건너뜁니다.")

train_full = df_labeled_raw[['공연/행사명', '대분류', '소분류 1 수동매핑']].copy()
train_full = train_full[train_full['소분류 1 수동매핑'].astype(str).str.strip() != '']
train_full = train_full.dropna(subset=['공연/행사명', '소분류 1 수동매핑']).reset_index(drop=True)
train_full = train_full.rename(columns={'소분류 1 수동매핑': LABEL_COL_K1, '대분류': '분류'})
train_full['공연/행사명'] = train_full['공연/행사명'].astype(str).str.strip()

if not df_raw.empty:
    df_raw['공연/행사명'] = df_raw['공연/행사명'].astype(str).str.strip()
    raw_cols_to_keep = ['공연/행사명', '출연자정보', '프로그램소개', '소개', '프로그램소개_크롤링', '기타내용', '장소']
    available_cols   = [c for c in raw_cols_to_keep if c in df_raw.columns]
    raw_features     = df_raw[available_cols].copy()
    raw_features     = raw_features.drop_duplicates(subset=['공연/행사명'], keep='first')
    train_full       = pd.merge(train_full, raw_features, on='공연/행사명', how='left')
    print(f"  [완료] 학습 데이터에 원본 텍스트 병합 성공!")

train_full = clean_text_cols(train_full)
df_events  = clean_text_cols(df_events)

# 가상 데이터 흡수
def load_synthetic(path):
    for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
        try:
            df = pd.read_csv(path, encoding=enc)
            return df, enc
        except UnicodeDecodeError:
            continue
        except Exception:
            raise
    return None, None

print(f"\n  [가상 데이터] 탐색 경로: {SYNTHETIC_PATH}")
try:
    if not os.path.exists(SYNTHETIC_PATH):
        raise FileNotFoundError(SYNTHETIC_PATH)
    df_fake, used_enc = load_synthetic(SYNTHETIC_PATH)
    if df_fake is None:
        raise UnicodeDecodeError('all', b'', 0, 1, "모든 인코딩 실패")
    df_fake   = df_fake.rename(columns={'소분류 1 수동매핑': LABEL_COL_K1, '대분류': '분류'})
    df_fake   = clean_text_cols(df_fake)
    train_full = pd.concat([train_full, df_fake], ignore_index=True)
    print(f"  ✨ [데이터 증강 성공] 가상 데이터 {len(df_fake)}건 주입!")
except FileNotFoundError:
    print(f"  [경고] synthetic_data.csv 없음 → 기존 {len(train_full)}건으로 진행")
except Exception as e:
    print(f"  [경고] {e} → 기존 {len(train_full)}건으로 진행")

print(f"\n  [최종 학습 가능 데이터]: {len(train_full)}건\n")


# =========================================================
# STEP 2. 모델 로드 및 임베딩 사전 생성
# =========================================================
print("🤖 [STEP 2] 모델 로드 및 임베딩 준비")
model = SentenceTransformer('jhgan/ko-sroberta-multitask')
print("  모델 로드 완료")

SUB_EMBS = {}
for sub_key, sub_dict in SUB_DICT.items():
    names = list(sub_dict.keys())
    descs = list(sub_dict.values())
    embs  = model.encode(descs, convert_to_tensor=True)
    SUB_EMBS[sub_key] = {"names": names, "embs": embs}
print("  임베딩 사전 생성 완료")


# =========================================================
# STEP 3. 성능 평가 (8:2 분할)
# =========================================================
print("\n📊 [STEP 3] 분류기 단일 모듈 vs 하이브리드 성능 평가")
print("=" * 60)

try:
    train_idx, val_idx = train_test_split(
        train_full.index, test_size=VAL_SIZE,
        stratify=train_full[LABEL_COL_K1], random_state=RANDOM_STATE
    )
except ValueError:
    print("  [경고] 클래스별 데이터 부족으로 랜덤 분할 수행")
    train_idx, val_idx = train_test_split(
        train_full.index, test_size=VAL_SIZE, random_state=RANDOM_STATE
    )

train_df = train_full.loc[train_idx].reset_index(drop=True)
val_df   = train_full.loc[val_idx].reset_index(drop=True)
print(f"  학습: {len(train_df)}건 / 검증: {len(val_df)}건\n")

print("  임베딩 추출 중...")
train_emb = model.encode([build_text(r) for _, r in train_df.iterrows()], batch_size=64)
val_emb   = model.encode([build_text(r) for _, r in val_df.iterrows()], batch_size=64)

le_val  = LabelEncoder()
le_val.fit(train_df[LABEL_COL_K1])
clf_val = LogisticRegression(C=1.2, max_iter=3000, class_weight='balanced', random_state=RANDOM_STATE)
clf_val.fit(train_emb, le_val.transform(train_df[LABEL_COL_K1]))

rule_preds, sem_preds, ml_preds, hybrid_preds, hybrid_reasons = [], [], [], [], []
rule_coverage = 0

for i, (_, row) in enumerate(val_df.iterrows()):
    key           = get_genre_key(row)
    text          = build_text(row)
    valid_subcats = list(SUB_DICT.get(key, {"기타": "기타"}).keys())
    sub_info      = SUB_EMBS.get(key) or SUB_EMBS["기타"]

    rule_res = rule_match_scored(text, SUB_RULES.get(key, {}))
    if rule_res and rule_res in valid_subcats:
        rule_preds.append(rule_res)
        rule_coverage += 1
    else:
        rule_preds.append("매핑불가")

    sem_res, _ = semantic_top(text, sub_info["names"], sub_info["embs"], threshold=0.0)
    sem_preds.append(sem_res if sem_res in valid_subcats else "기타")

    probas = clf_val.predict_proba([val_emb[i]])[0]
    b_idx, b_prob = -1, -1.0
    for idx, c_name in enumerate(le_val.classes_):
        if c_name in valid_subcats and probas[idx] > b_prob:
            b_prob = probas[idx]
            b_idx  = idx
    ml_preds.append(le_val.classes_[b_idx] if b_idx != -1 else "기타")

    hyb_res, hyb_reason = hybrid_classify_k1(row, val_emb[i], clf_val, le_val)
    hybrid_preds.append(hyb_res)
    hybrid_reasons.append(hyb_reason)

y_true = val_df[LABEL_COL_K1].astype(str).reset_index(drop=True)

# BUG FIX: rule_acc 계산
if rule_coverage > 0:
    rule_mask            = [p != "매핑불가" for p in rule_preds]
    y_true_rule          = y_true[rule_mask].reset_index(drop=True)
    rule_preds_filtered  = [p for p in rule_preds if p != "매핑불가"]
    rule_acc             = accuracy_score(y_true_rule, rule_preds_filtered)
else:
    rule_acc = 0.0

sem_acc = accuracy_score(y_true, sem_preds)
ml_acc  = accuracy_score(y_true, ml_preds)
hyb_acc = accuracy_score(y_true, hybrid_preds)

print("\n🏆 [평가 결과 리포트]")
print(f"  1. 규칙(Rule) 단독    : 정확도 {rule_acc*100:5.1f}% (커버리지 {rule_coverage/len(val_df)*100:.1f}%)")
print(f"  2. 임베딩(Sem) 단독   : 정확도 {sem_acc*100:5.1f}%")
print(f"  3. 머신러닝(ML) 단독  : 정확도 {ml_acc*100:5.1f}%")
print(f"  4. 하이브리드(Hybrid) : 정확도 {hyb_acc*100:5.1f}%")
print("=" * 60)

# ─── 오답 노트 ───────────────────────────────────────────
print("\n🚨 [오답 노트] 하이브리드 모델이 헷갈려 한 케이스")
count = 0
for i, (pred_ml, pred_hyb, true_label) in enumerate(zip(ml_preds, hybrid_preds, y_true)):
    if pred_hyb != true_label:
        title = val_df.iloc[i]['공연/행사명']
        print(f" - [행사명] {title}")
        print(f"   ㄴ 실제정답: {true_label} ✅")
        print(f"   ㄴ 모델예측: {pred_hyb} ❌  (ML단독: {pred_ml})")
        count += 1
        if count >= 10:
            break
print("=" * 60)

# =========================================================
# ✅ [추가] 오분류 패턴 분석
# =========================================================
print("\n🔍 [오분류 패턴 분석]")
print("=" * 60)

# 소분류 → 장르 역매핑 테이블
SUB_TO_GENRE = {}
for genre, sub_dict in SUB_DICT.items():
    for sub in sub_dict.keys():
        SUB_TO_GENRE[sub] = genre

# 하이브리드 예측 결과 데이터프레임 구성
val_result = val_df.copy()
val_result["pred"]   = hybrid_preds
val_result["reason"] = hybrid_reasons
val_result["y_true"] = y_true.values

wrong = val_result[val_result["y_true"] != val_result["pred"]].copy()
wrong["정답_장르"] = wrong["y_true"].map(SUB_TO_GENRE)
wrong["예측_장르"] = wrong["pred"].map(SUB_TO_GENRE)

# ① 장르 내 vs 장르 간 오분류
same_genre  = wrong[wrong["정답_장르"] == wrong["예측_장르"]]
cross_genre = wrong[wrong["정답_장르"] != wrong["예측_장르"]]

print(f"\n  전체 오분류:    {len(wrong)}건 / {len(val_df)}건")
if len(wrong) > 0:
    print(f"  장르 내 오분류: {len(same_genre)}건 ({len(same_genre)/len(wrong)*100:.1f}%)  ← 덜 심각")
    print(f"  장르 간 오분류: {len(cross_genre)}건 ({len(cross_genre)/len(wrong)*100:.1f}%)  ← 심각")

# ② 장르 간 오분류 패턴
if len(cross_genre) > 0:
    print(f"\n  [장르 간 오분류 패턴]")
    pattern = cross_genre.groupby(["정답_장르", "예측_장르"]).size().sort_values(ascending=False)
    for (true_g, pred_g), cnt in pattern.items():
        print(f"    {true_g}  →  {pred_g}: {cnt}건")

# ③ 소분류 간 오분류 패턴 상위 10개
print(f"\n  [소분류 간 오분류 패턴 상위 10개]")
sub_pattern = wrong.groupby(["y_true", "pred"]).size().sort_values(ascending=False).head(10)
for (true_s, pred_s), cnt in sub_pattern.items():
    severity = "⚠️ 심각" if SUB_TO_GENRE.get(true_s) != SUB_TO_GENRE.get(pred_s) else "✅ 경미"
    print(f"    {severity}  {true_s}  →  {pred_s}: {cnt}건")

# ④ 판단 경로별 정확도
print(f"\n  [판단 경로별 정확도]")
for reason in val_result["reason"].unique():
    mask    = val_result["reason"] == reason
    r_true  = val_result.loc[mask, "y_true"]
    r_pred  = val_result.loc[mask, "pred"]
    r_acc   = accuracy_score(r_true, r_pred)
    print(f"    {reason:25s}: {r_acc*100:.1f}%  ({mask.sum()}건)")

# ⑤ 최종 도입 판단
cross_ratio = len(cross_genre) / len(wrong) * 100 if len(wrong) > 0 else 0
print(f"\n  [📌 도입 판단]")
if cross_ratio < 10:
    print(f"  ✅ 장르 간 오분류 {cross_ratio:.1f}% → 도입 확정")
elif cross_ratio < 20:
    print(f"  ⚠️ 장르 간 오분류 {cross_ratio:.1f}% → 조건부 도입 (패턴 확인 권장)")
else:
    print(f"  ❌ 장르 간 오분류 {cross_ratio:.1f}% → 재검토 필요")

print("=" * 60)


# =========================================================
# STEP 4. 전수 학습 (Full Training)
# =========================================================
print(f"\n🚀 [STEP 4] 전수 학습 (데이터 {len(train_full)}건 전체 활용)")

full_emb = model.encode(
    [build_text(r) for _, r in train_full.iterrows()],
    batch_size=64, show_progress_bar=True
)

le_k1  = LabelEncoder()
le_k1.fit(train_full[LABEL_COL_K1])
clf_k1 = LogisticRegression(C=1.2, max_iter=3000, class_weight='balanced', random_state=RANDOM_STATE)
clf_k1.fit(full_emb, le_k1.transform(train_full[LABEL_COL_K1]))

joblib.dump((clf_k1, le_k1), os.path.join(CLASSIFIER_DIR, 'clf_k1.pkl'))
print(f"  [저장 완료] 최종 분류기 모델: {CLASSIFIER_DIR}clf_k1.pkl")


# =========================================================
# STEP 5. 실전 투입 (전체 행사 분류)
# =========================================================
print(f"\n🔮 [STEP 5] 실전 투입 - 전체 행사 분류 ({len(df_events)}건)")

events_emb = model.encode(
    [build_text(r) for _, r in df_events.iterrows()],
    batch_size=64, show_progress_bar=True
)

mapped_results, mapped_reasons = [], []
for i, (_, row) in enumerate(tqdm(df_events.iterrows(), total=len(df_events))):
    pred, reason = hybrid_classify_k1(row, events_emb[i], clf_k1, le_k1)
    mapped_results.append(pred)
    mapped_reasons.append(reason)

df_events["소분류"]      = mapped_results
df_events["소분류_근거"] = mapped_reasons


# =========================================================
# STEP 6. 결과 저장 및 요약
# =========================================================
print("\n💾 [STEP 6] 결과 저장")
df_events.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
print(f"  [저장 완료] 결과 파일: {OUTPUT_PATH}")

print("\n📊 [소분류 분포]")
print(df_events["소분류"].value_counts().to_string())

print("\n📊 [판단 경로 분포]")
print(df_events["소분류_근거"].value_counts().to_string())

print("\n✅ 모든 과정이 성공적으로 완료되었습니다!")