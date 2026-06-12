import requests
import pandas as pd
import time
import random
import re
from bs4 import BeautifulSoup
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# =========================================================================
# [설정]
# =========================================================================
API_KEY = os.getenv("SEOUL_API_KEY", "YOUR_SEOUL_KEY")
SERVICE = "culturalEventInfo"
CURRENT_DATE = datetime(2026, 6, 5).date()

PAGE_SIZE = 50

SUCCESS_MIN_LEN = 200

STATUS_SUCCESS = "성공"
STATUS_PARTIAL = "부분성공(글자수부족)"
STATUS_EMPTY   = "데이터없음"
STATUS_FAILED  = "실패(에러)"

SOURCE_TEXT = "본문텍스트"
SOURCE_ALT  = "이미지ALT"
SOURCE_NONE = "없음"


# =========================================================================
# [텍스트 정제 함수]
# =========================================================================
_PREFIX_NOISE = re.compile(
    r'^서울의 모든 순간이 축제가 됩니다\.\s*펀서울\s*'
)
_NOISE_BLOCK = re.compile(
    r'(?:자료출처\s*:?\s*[^\n※]+)?\s*'
    r'※\s*해당 행사 상세 정보는 상단의\s*[\'’"“]?홈페이지 바로가기[\'’"“]?\s*'
    r'에\s*서?\s*참\s*고\s*부탁드립니다\.?\s*'
    r'서울의 모든 순간이 축제가 됩니다\.\s*펀서울\s*'
)
_TAIL_NOISE = re.compile(
    r'\(사\)한국장애인단체총연합회\s*한국웹접근성인증평가원\s*'
    r'웹접근성\s*우수사이트\s*인증마크\(WA인증마크\)\s*$'
)

def remove_duplicate_block(text: str, min_len: int = 100) -> str:
    """앞 min_len자 블록이 본문 중간에 재등장하면 첫 번째만 남기고 제거"""
    if len(text) < min_len * 2:
        return text
    chunk = text[:min_len]
    second = text.find(chunk, min_len)
    if second != -1:
        return (text[:second] + text[second + min_len:]).strip()
    return text

def clean_text(text: str) -> str:
    """노이즈 문구 제거 후 순수 본문 반환"""
    if not isinstance(text, str) or not text.strip():
        return ""
    text = _PREFIX_NOISE.sub("", text)
    text = _NOISE_BLOCK.sub("", text)
    text = _TAIL_NOISE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# =========================================================================
# [크롤링 함수] ALT텍스트 → 본문텍스트 2단계 전략 + 상태 추적
# =========================================================================
def crawl_detail(url, headers):
    result = {
        '프로그램소개_크롤링': '',
        '크롤링_소스': SOURCE_NONE,
        '크롤링_상태': STATUS_EMPTY
    }

    if pd.isna(url) or not str(url).startswith('http'):
        result['크롤링_상태'] = "URL없음"
        return result

    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            result['크롤링_상태'] = f"접근실패({res.status_code})"
            return result

        soup = BeautifulSoup(res.text, 'html.parser')

        # ── [1단계] 이미지 ALT 텍스트 수집 ──────────────────────────────────
        alt_texts = []
        for img in soup.select('img[alt]'):
            alt = img.get('alt', '').strip()
            if len(alt) > 10 and not any(k in alt for k in ['페이스북', '카카오', '트위터', '인쇄', '공유', 'sns', '로고', 'instagram']):
                alt_texts.append(alt)

        alt_combined = ' '.join(alt_texts).strip()
        refined_alt = remove_duplicate_block(alt_combined)
        refined_alt = clean_text(refined_alt)

        if len(refined_alt) >= SUCCESS_MIN_LEN:
            result['프로그램소개_크롤링'] = refined_alt
            result['크롤링_소스'] = SOURCE_ALT
            result['크롤링_상태'] = STATUS_SUCCESS
            return result

        # ── [2단계] ALT 실패 시 본문 텍스트 수집 ────────────────────────────
        body_text = ''
        for selector in ['.view_content', '#detail', '.event_detail', '.cont_detail', '.view_con', '#contents', '.detail_txt']:
            section = soup.select_one(selector)
            if section:
                body_text = section.get_text(separator=' ', strip=True)
                break

        if not body_text:
            for h in soup.find_all(['h3', 'h4']):
                if '상세' in h.get_text():
                    sibling = h.find_next_sibling()
                    if sibling:
                        body_text = sibling.get_text(separator=' ', strip=True)
                        break

        refined_body = remove_duplicate_block(body_text.strip())
        refined_body = clean_text(refined_body)

        # ── [3단계] 최종 판정 ────────────────────────────────────────────────
        if len(refined_body) >= SUCCESS_MIN_LEN:
            result['프로그램소개_크롤링'] = refined_body
            result['크롤링_소스'] = SOURCE_TEXT
            result['크롤링_상태'] = STATUS_SUCCESS

        elif len(refined_body) > 0 or len(refined_alt) > 0:
            if len(refined_body) >= len(refined_alt):
                result['프로그램소개_크롤링'] = refined_body
                result['크롤링_소스'] = SOURCE_TEXT
            else:
                result['프로그램소개_크롤링'] = refined_alt
                result['크롤링_소스'] = SOURCE_ALT
            result['크롤링_상태'] = STATUS_PARTIAL

        else:
            result['크롤링_상태'] = STATUS_EMPTY
            result['크롤링_소스'] = SOURCE_NONE

    except Exception as e:
        # ✅ [보완 3] 에러 원인 로깅 추가
        result['크롤링_상태'] = f"실패({type(e).__name__})"
        result['크롤링_소스'] = SOURCE_NONE

    return result


# =========================================================================
# [메인] API 수집 + 크롤링 통합
# =========================================================================
def fetch_seoul_events_test():
    print(f"🚀 서울 Open API 전체 수집 시작 (기준일: {CURRENT_DATE})")
    results = []
    start_index = 1
    collected_titles = set()  # ✅ [보완 2] 실시간 중복 체크용

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    while True:
        end_index = start_index + PAGE_SIZE - 1
        print(f"\nAPI 호출 중: {start_index} ~ {end_index} (현재까지 수집: {len(results)}건)")

        # ✅ [보완 1] API 호출 에러 처리 추가
        try:
            res = requests.get(
                f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/{start_index}/{end_index}/",
                timeout=10
            )
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            print(f"  API 호출 실패 ({type(e).__name__}): {e}")
            break

        if SERVICE not in data or not data[SERVICE].get("row"):
            print("더 이상 API 데이터 없음. 종료.")
            break

        rows = data[SERVICE]["row"]

        for row in rows:

            # ✅ [보완 2] 실시간 중복 체크
            title = row.get("TITLE")
            if title in collected_titles:
                print(f"  중복 항목 건너뜀: {title}")
                continue
            collected_titles.add(title)

            # 날짜 필터링 (형식 오류 시 포함)
            end_date_raw = str(row.get("END_DATE", "")).split(" ")[0]
            try:
                end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
                if end_date < CURRENT_DATE:
                    continue
            except ValueError:
                # ✅ [보완 3] 날짜 오류 원인 로깅, 날짜 불명확 항목은 포함
                print(f"  날짜 형식 오류 ({end_date_raw}), 포함 처리")

            event_data = {
                "분류":             row.get("CODENAME"),
                "자치구":           row.get("GUNAME"),
                "공연/행사명":      row.get("TITLE"),
                "시작일":           row.get("STRTDATE"),
                "종료일":           row.get("END_DATE"),
                "장소":             row.get("PLACE"),
                "위도":             row.get("LAT"),
                "경도":             row.get("LOT"),
                "이용대상":         row.get("USE_TRGT"),
                "이용요금":         row.get("USE_FEE"),
                "유무료":           row.get("IS_FREE"),
                "대표이미지":       row.get("MAIN_IMG"),
                "홈페이지주소":     row.get("ORG_LINK"),
                "문화포털상세URL":  row.get("HMPG_ADDR"),
                "프로그램소개":     row.get("PROGRAM"),
            }

            crawl_res = crawl_detail(row.get("HMPG_ADDR"), headers)
            event_data['프로그램소개_크롤링'] = crawl_res['프로그램소개_크롤링']
            event_data['크롤링_소스']         = crawl_res['크롤링_소스']
            event_data['크롤링_상태']         = crawl_res['크롤링_상태']

            print(f"  [{len(results)+1:02d}] {title} | {crawl_res['크롤링_상태']} ({crawl_res['크롤링_소스']})")

            results.append(event_data)

            # 차단 감지 시 5초 대기, 정상 시 1.0~1.5초 딜레이
            if crawl_res['크롤링_상태'] in ("접근실패(403)", "접근실패(429)"):
                print("  ⚠️ 차단 패턴 감지! 5초 대기...")
                time.sleep(5.0)
            else:
                time.sleep(random.uniform(1.0, 1.5))

        start_index += PAGE_SIZE

    df = pd.DataFrame(results)
    df.to_csv("seoul_raw.csv", index=False, encoding="utf-8-sig")

    print(f"\n✅ 수집 완료: seoul_raw.csv ({len(df)}건 저장)")
    print("\n--- 크롤링 결과 요약 ---")
    print(df['크롤링_상태'].value_counts().to_string())


if __name__ == "__main__":
    fetch_seoul_events_test()