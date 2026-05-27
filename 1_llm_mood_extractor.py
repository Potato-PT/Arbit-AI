import os
import json
import time
import pandas as pd
from tqdm import tqdm
from google import genai
from google.genai import types
from dotenv import load_dotenv

# .env 파일에서 API 키 로드
load_dotenv()

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
INPUT_CSV   = "seoul_events_preprocessed.csv"
OUTPUT_CSV  = "events_with_mood.csv"
CACHE_PATH  = "mood_cache.json"

MODEL       = "gemini-3.1-flash-lite"
API_DELAY   = 5.0
MAX_RETRIES = 3
CHUNK_SIZE  = 500

# 무드 분류용 상수
# [수정] "기타" 제거 — 6가지 태그만 유효
MOOD_TAGS_VALID = ["힐링/감성", "신나는/활기찬", "감동/웅장", "전통/문화", "가족친화", "학술/사색적"]

MOOD_KEYWORDS = {
    "힐링/감성":    ["힐링", "감성", "치유", "명상", "잔잔", "평화", "위로"],
    "신나는/활기찬": ["신나는", "활기", "신명", "흥겨", "즐거운", "에너지", "축제"],
    "감동/웅장":    ["감동", "웅장", "압도", "장엄", "웅대", "합창", "오케스트라"],
    "전통/문화":    ["전통", "국악", "민속", "고전", "한국", "궁중", "역사", "아리랑"],
    "가족친화":     ["가족", "어린이", "아이", "자녀", "온 가족", "키즈"],
    "학술/사색적":  ["학술", "사색", "강연", "교육", "체험", "배움", "철학"],
}

# [수정] 프롬프트에서 "기타" 옵션 제거
# → 반드시 6가지 태그 중에서만 선택하도록 강제
MOOD_SYSTEM_PROMPT = """당신은 서울 문화행사 무드 분류 전문가입니다.

[무드 태그 정의]
- 힐링/감성: 치유적, 감성적, 잔잔한, 평화로운 행사
- 신나는/활기찬: 흥겨운, 신명나는, 활기찬 행사
- 감동/웅장: 감동적인, 웅장한, 압도적인 규모의 행사
- 전통/문화: 한국 전통, 국악, 역사, 문화유산 관련 행사
- 가족친화: 가족 단위, 어린이와 함께 즐기기 적합한 행사
- 학술/사색적: 강연, 교육, 체험 학습 행사

[규칙]
1. 반드시 위 6가지 태그 중에서만 1~3개를 선택하세요.
2. 명확하지 않더라도 행사 성격에 가장 가까운 태그를 반드시 선택해야 합니다.
3. "기타" 또는 6가지 외의 태그는 절대 사용하지 마세요.
4. JSON 형식으로만 응답하세요. (형식: {"mood_tags": ["태그명"]})"""

# ──────────────────────────────────────────────
# 핵심 로직
# ──────────────────────────────────────────────

# [수정] 키워드 매칭 실패 시 "기타" 대신 "힐링/감성"을 기본값으로 반환
# → 문화행사 특성상 가장 범용적인 태그로 설정
def extract_mood_rule(text):
    tags = [mood for mood, kws in MOOD_KEYWORDS.items() if any(kw in text for kw in kws)]
    return tags if tags else ["힐링/감성"]

# [수정] 유효하지 않은 태그(기타 포함) 걸러낸 후 비어있으면 "힐링/감성" 기본값 반환
def parse_llm_mood(content):
    try:
        s, e = content.find("{"), content.rfind("}") + 1
        if s >= 0 and e > s:
            tags = json.loads(content[s:e]).get("mood_tags", [])
            valid = set(MOOD_TAGS_VALID)
            filtered = [t for t in tags if t in valid]
            return filtered if filtered else ["힐링/감성"]
    except:
        pass
    return ["힐링/감성"]


# ──────────────────────────────────────────────
# LLM 호출 함수 (extract_info.py 검증 방식 적용)
# ──────────────────────────────────────────────
def call_llm_with_retry(client, model, prompt, config):
    """
    에러 분기:
      - "per day" / "daily"          → 일일 한도 초과, 전체 중단
      - 429 / RESOURCE_EXHAUSTED
        / "quota"                    → RPM 초과, 60*attempt초 대기 후 재시도
      - 503                          → 서버 일시 오류, 10초 대기 후 재시도
      - 그 외                         → 즉시 rule fallback
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            res = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            return res.text, "llm"

        except Exception as e:
            err_str = str(e)
            print(f"\n[DEBUG] 전체 에러 메시지: {err_str}")

            if "per day" in err_str.lower() or "daily" in err_str.lower():
                print(f"\n⛔ 일일 할당량(RPD) 초과. 이후 행사는 Rule 기반으로 전환합니다.")
                return None, "quota_exceeded"

            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                wait = 60 * attempt
                print(f"\n⚠ Rate Limit 감지. {wait}초 대기 후 재시도... ({attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                continue

            if "503" in err_str:
                print(f"\n🔄 서버 일시 오류. 10초 대기 후 재시도... ({attempt}/{MAX_RETRIES})")
                time.sleep(10)
                continue

            print(f"\n🚨 예상치 못한 에러: {err_str}")
            return None, "rule"

    print(f"\n⚠ 최대 재시도 횟수({MAX_RETRIES}회) 초과. Rule 기반으로 처리합니다.")
    return None, "rule"


def main():
    print("🚀 [STEP 2] LLM 무드 추출을 시작합니다...")

    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"❌ 전처리된 파일이 없습니다. '0_data_processing.py'를 먼저 실행하세요.")
        return

    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    use_llm = bool(api_key)
    client = genai.Client(api_key=api_key) if use_llm else None

    target_indices = [i for i, row in df.iterrows() if str(row['event_id']) not in cache]
    targets_to_process = target_indices[:CHUNK_SIZE]

    print(f"\n📊 총 행사: {len(df)}건 / 무드 추출 대상: {len(target_indices)}건")

    if targets_to_process and use_llm:
        print(f"⏳ 이번에 처리할 건수: {len(targets_to_process)}건 (약 {int(len(targets_to_process) * API_DELAY / 60)}분 소요)")

        config = types.GenerateContentConfig(
            system_instruction=MOOD_SYSTEM_PROMPT,
            max_output_tokens=150, temperature=0.1, response_mime_type="application/json"
        )

        count = 0
        quota_exceeded = False

        try:
            for idx in tqdm(targets_to_process, desc="무드 추출 중"):
                if quota_exceeded:
                    row = df.loc[idx]
                    eid = str(row["event_id"])
                    cache[eid] = {"tags": extract_mood_rule(row["description"]), "source": "rule"}
                    continue

                row = df.loc[idx]
                eid = str(row["event_id"])
                prompt_input = f"행사 제목: {row['title']}\n장르: {row['genre']}\n상세 설명: {row['description']}"

                llm_text, source = call_llm_with_retry(
                    client, MODEL,
                    f"다음 문화행사의 분위기(무드)를 분류해주세요.\n\n{prompt_input[:1200]}",
                    config
                )

                if source == "llm":
                    cache[eid] = {"tags": parse_llm_mood(llm_text), "source": "llm"}
                elif source == "quota_exceeded":
                    cache[eid] = {"tags": extract_mood_rule(row["description"]), "source": "rule"}
                    quota_exceeded = True
                else:
                    cache[eid] = {"tags": extract_mood_rule(row["description"]), "source": "rule"}

                count += 1
                time.sleep(API_DELAY)

                if count % 50 == 0:
                    with open(CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(cache, f, ensure_ascii=False)

        except KeyboardInterrupt:
            print("\n🛑 사용자에 의해 중단되었습니다.")
        finally:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)

    elif not use_llm:
        print("⚠ API 키가 등록되지 않아 전체 규칙 기반(Rule)으로 작동합니다.")
        for i, row in df.iterrows():
            eid = str(row['event_id'])
            if eid not in cache:
                cache[eid] = {"tags": extract_mood_rule(row["description"]), "source": "rule"}

    df["mood_tags"] = df["event_id"].apply(lambda x: ",".join(cache.get(str(x), {}).get("tags", ["힐링/감성"])))
    df["mood_source"] = df["event_id"].apply(lambda x: cache.get(str(x), {}).get("source", "unknown"))

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n✅ 완료! 추천에 사용할 최종 파일이 저장되었습니다: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()