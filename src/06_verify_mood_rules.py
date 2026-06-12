"""
verify_mood_rules.py
─────────────────────────────────────────────────────────────
소분류 → 무드 규칙 테이블 검증 스크립트

목적:
  1. events_with_subgenre.csv의 소분류 컬럼과 SUB_TO_MOOD 커버리지 확인
  2. 미매핑 소분류 탐지 (규칙 추가 필요 항목)
  3. 무드 태그 분포 통계 출력
  4. 장르 × 무드 크로스탭 출력
  5. 무드 컬럼이 추가된 CSV 저장 (events_with_mood.csv)

실행:
  python verify_mood_rules.py

출력:
  - 콘솔: 단계별 검증 리포트
  - events_with_mood.csv: 무드_태그 / 무드_1 / 무드_2 컬럼 추가된 파일
"""

import pandas as pd
from collections import Counter

# ═══════════════════════════════════════════════
# 0. 설정
# ═══════════════════════════════════════════════
INPUT_FILE  = "events_with_subgenre.csv"
OUTPUT_FILE = "events_with_mood.csv"
SUB_COL     = "소분류"          # 1_classifier.py 출력 컬럼명 (다르면 수정)
GENRE_COL   = "장르"
FALLBACK_MOOD = ["힐링/감성"]   # 미매핑 소분류 기본값


# ═══════════════════════════════════════════════
# 1. 규칙 테이블 (SUB_TO_MOOD)
# ═══════════════════════════════════════════════
SUB_TO_MOOD = {
    # 클래식
    "관현악/교향곡":        ["감동/웅장", "힐링/감성"],
    "기악 독주회":          ["힐링/감성", "감동/웅장"],
    "실내악/앙상블":        ["힐링/감성", "감동/웅장"],
    # 콘서트
    "재즈/크로스오버":      ["힐링/감성", "신나는/활기찬"],
    "대중/인디 음악":       ["신나는/활기찬", "힐링/감성"],
    "고궁/야외 콘서트":     ["힐링/감성", "전통/문화"],
    "성악/팝페라":          ["감동/웅장"],
    # 연극
    "아동/가족극":          ["가족친화", "신나는/활기찬"],
    "기획/프로젝트극":      ["학술/사색적", "감동/웅장"],
    "정통 연극/극단전":     ["학술/사색적", "감동/웅장"],
    # 뮤지컬/오페라
    "뮤지컬":               ["신나는/활기찬", "감동/웅장"],
    "오페라":               ["감동/웅장"],
    # 무용
    "발레":                 ["감동/웅장", "힐링/감성"],
    "현대/창작무용":        ["학술/사색적", "힐링/감성"],
    "전통무용":             ["전통/문화", "힐링/감성"],
    # 국악
    "전통 국악":            ["전통/문화", "힐링/감성"],
    "창작/퓨전 국악":       ["신나는/활기찬", "전통/문화"],
    # 교육/체험
    "만들기/공방 체험":     ["가족친화", "힐링/감성"],
    "도서/독서 연계":       ["학술/사색적", "힐링/감성"],
    "학술/강연":            ["학술/사색적"],
    # 축제
    "야외 체험 행사":       ["신나는/활기찬", "가족친화"],
    "종합 문화 페스티벌":   ["신나는/활기찬", "가족친화"],
    "체험/참여형 축제":     ["신나는/활기찬", "가족친화"],
    "기념/역사 축제":       ["전통/문화", "학술/사색적"],
    # 전시/미술
    "개인전/초대전":        ["힐링/감성", "학술/사색적"],
    "기획/테마 전시":       ["학술/사색적", "힐링/감성"],
    "역사/문화/산업":       ["전통/문화", "학술/사색적"],
    # 영화
    "특별 상영회/페스타":   ["힐링/감성", "신나는/활기찬"],
    "고전/독립/예술 영화":  ["학술/사색적", "힐링/감성"],
    # 기타
    "기타":                 ["힐링/감성"],
}

ALL_MOODS = ["힐링/감성", "감동/웅장", "신나는/활기찬", "전통/문화", "학술/사색적", "가족친화"]


# ═══════════════════════════════════════════════
# 2. 데이터 로드
# ═══════════════════════════════════════════════
print("=" * 60)
print("  verify_mood_rules.py — 무드 규칙 테이블 검증")
print("=" * 60)

try:
    df = pd.read_csv(INPUT_FILE)
    print(f"\n✅ 파일 로드 성공: {INPUT_FILE}  ({len(df):,}건)\n")
except FileNotFoundError:
    print(f"\n❌ 파일 없음: {INPUT_FILE}")
    print("   → 1_classifier.py 실행 후 다시 시도하세요.\n")
    exit(1)

# 소분류 컬럼 존재 확인
if SUB_COL not in df.columns:
    print(f"❌ '{SUB_COL}' 컬럼 없음. 실제 컬럼명을 확인하세요.")
    print(f"   현재 컬럼 목록: {list(df.columns)}\n")
    exit(1)


# ═══════════════════════════════════════════════
# 3. [검증 1] 소분류 커버리지
# ═══════════════════════════════════════════════
data_subs   = set(df[SUB_COL].dropna().unique())
rule_subs   = set(SUB_TO_MOOD.keys())
covered     = data_subs & rule_subs
not_covered = data_subs - rule_subs   # 데이터에 있는데 규칙이 없는 것
unused      = rule_subs - data_subs   # 규칙에 있는데 데이터에 없는 것

print("─" * 60)
print("[검증 1] 소분류 커버리지")
print("─" * 60)
print(f"  데이터 내 소분류 종류  : {len(data_subs):2}개")
print(f"  규칙 테이블 소분류     : {len(rule_subs):2}개")
print(f"  ✅ 매핑 완료           : {len(covered):2}개")

if not_covered:
    print(f"\n  ⚠️  미매핑 소분류 ({len(not_covered)}개) — SUB_TO_MOOD 추가 필요")
    for s in sorted(not_covered):
        count = (df[SUB_COL] == s).sum()
        print(f"     - '{s}'  ({count}건)  → fallback: {FALLBACK_MOOD}")
else:
    print("  ✅ 미매핑 소분류 없음 — 전체 커버")

if unused:
    print(f"\n  ℹ️  데이터에 미존재 규칙 ({len(unused)}개) — 제거 검토 가능")
    for s in sorted(unused):
        print(f"     - '{s}'")


# ═══════════════════════════════════════════════
# 4. 무드 태그 부착
# ═══════════════════════════════════════════════
def get_moods(sub):
    """소분류 → 무드 리스트 반환. 미매핑이면 FALLBACK_MOOD."""
    if pd.isna(sub):
        return FALLBACK_MOOD
    return SUB_TO_MOOD.get(str(sub).strip(), FALLBACK_MOOD)

df["무드_태그"] = df[SUB_COL].apply(get_moods)
df["무드_1"]   = df["무드_태그"].apply(lambda x: x[0])
df["무드_2"]   = df["무드_태그"].apply(lambda x: x[1] if len(x) > 1 else None)

# 리스트를 CSV 저장용 문자열로 변환 (파이프 구분)
df["무드_태그_str"] = df["무드_태그"].apply(lambda x: "|".join(x))


# ═══════════════════════════════════════════════
# 5. [검증 2] 무드 태그 분포
# ═══════════════════════════════════════════════
print("\n" + "─" * 60)
print("[검증 2] 무드 태그 분포 (다중 태그 포함)")
print("─" * 60)

mood_counter = Counter()
for moods in df["무드_태그"]:
    for m in moods:
        mood_counter[m] += 1

total_tags = sum(mood_counter.values())
for mood in ALL_MOODS:
    cnt  = mood_counter.get(mood, 0)
    pct  = cnt / total_tags * 100
    bar  = "█" * int(pct / 2.5)   # 40칸 기준
    print(f"  {mood:<16}  {cnt:5,}건  {pct:5.1f}%  {bar}")

print(f"\n  총 태그 수 (중복 포함) : {total_tags:,}건")
print(f"  총 행사 수             : {len(df):,}건")
print(f"  행사당 평균 태그 수    : {total_tags / len(df):.2f}개")

# 단일 태그만 부여된 행사 비율
single_tag = df["무드_태그"].apply(lambda x: len(x) == 1).sum()
print(f"  단일 태그 행사         : {single_tag:,}건 ({single_tag/len(df)*100:.1f}%)")
print(f"  다중 태그 행사         : {len(df)-single_tag:,}건 ({(len(df)-single_tag)/len(df)*100:.1f}%)")


# ═══════════════════════════════════════════════
# 6. [검증 3] 장르 × 무드_1 크로스탭
# ═══════════════════════════════════════════════
print("\n" + "─" * 60)
print("[검증 3] 장르 × 무드_1 크로스탭")
print("─" * 60)

if GENRE_COL in df.columns:
    cross = pd.crosstab(df[GENRE_COL], df["무드_1"], margins=True, margins_name="합계")
    print(cross.to_string())
else:
    print(f"  '{GENRE_COL}' 컬럼 없음 — 생략")


# ═══════════════════════════════════════════════
# 7. [검증 4] 소분류별 무드 매핑 전체 출력
# ═══════════════════════════════════════════════
print("\n" + "─" * 60)
print("[검증 4] 소분류별 무드 매핑 현황 (데이터 내 존재 항목)")
print("─" * 60)

sub_stats = df.groupby(SUB_COL).size().reset_index(name="건수")
sub_stats = sub_stats.sort_values("건수", ascending=False)

for _, row in sub_stats.iterrows():
    sub   = row[SUB_COL]
    cnt   = row["건수"]
    moods = SUB_TO_MOOD.get(sub, FALLBACK_MOOD)
    tag   = " / ".join(moods)
    mark  = "✅" if sub in rule_subs else "⚠️ "
    print(f"  {mark} {sub:<20} ({cnt:4}건) → {tag}")


# ═══════════════════════════════════════════════
# 8. 결과 저장
# ═══════════════════════════════════════════════
# 저장 시 리스트 컬럼은 문자열로 대체
df_out = df.drop(columns=["무드_태그"])
df_out = df_out.rename(columns={"무드_태그_str": "무드_태그"})

df_out.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

print("\n" + "─" * 60)
print("[결과 저장]")
print("─" * 60)
print(f"  ✅ {OUTPUT_FILE} 저장 완료")
print(f"     추가 컬럼: 무드_태그 (파이프 구분), 무드_1, 무드_2")

print("\n" + "=" * 60)
print("  검증 완료 — 결과 확인 후 SUB_TO_MOOD 수정하세요")
print("=" * 60)