import requests
import xml.etree.ElementTree as ET
import pandas as pd
import time
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

SERVICE_KEY = os.getenv("KOPIS_API_KEY", "YOUR_KOPIS_KEY")
CURRENT_DATE = datetime(2026, 6, 5).date()

def fetch_kopis_events_test():
    print(f"🚀 KOPIS 전체 수집 시작 (기준일: {CURRENT_DATE}, 서울 지역)")
    results = []
    page = 1
    collected_ids = set()  # ✅ [보완 2] 실시간 중복 체크용 (공연ID 기준)

    while True:
        print(f"목록 페이지 조회 중: {page} (현재까지 수집: {len(results)}건)")

        # ✅ [보완 1] 목록 API 호출 에러 처리 추가
        try:
            res = requests.get(
                "http://www.kopis.or.kr/openApi/restful/pblprfr",
                params={
                    "service":     SERVICE_KEY,
                    "stdate":      CURRENT_DATE.strftime("%Y%m%d"),
                    "eddate":      "20271231",
                    "cpage":       page,
                    "rows":        50,        # 최대(100)의 절반, 호출 제한 대비
                    "signgucode":  "11"       # API 단에서 서울만 수신
                },
                timeout=10
            )
            res.raise_for_status()
            root = ET.fromstring(res.text)
        except Exception as e:
            print(f"  목록 API 호출 실패 ({type(e).__name__}): {e}")
            break

        dbs = root.findall("db")
        if not dbs:
            print("더 이상 목록 데이터 없음. 종료.")
            break

        for db in dbs:

            mt20id = db.findtext("mt20id")
            prfnm  = db.findtext("prfnm")

            # ✅ [보완 2] 실시간 중복 체크
            if mt20id in collected_ids:
                print(f"  중복 항목 건너뜀: {prfnm}")
                continue
            collected_ids.add(mt20id)

            end_date_str = db.findtext("prfpdto")
            print(f"[DEBUG] 공연명: {prfnm} | 종료일: {end_date_str}")

            # 날짜 필터링 (형식 오류 시 포함)
            try:
                end_date = datetime.strptime(end_date_str, "%Y.%m.%d").date()
                if end_date < CURRENT_DATE:
                    print(f"  -> 날짜 필터링으로 통과 실패 ({end_date} < {CURRENT_DATE})")
                    continue
            except ValueError:
                # ✅ [보완 3] 날짜 오류 원인 로깅, 날짜 불명확 항목은 포함
                print(f"  -> 날짜 형식 오류 ({end_date_str}), 포함 처리")

            # ✅ [보완 1] 상세 API 호출 에러 처리 추가
            try:
                detail_res = requests.get(
                    f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}",
                    params={"service": SERVICE_KEY},
                    timeout=10
                )
                detail_res.raise_for_status()
                time.sleep(0.3)
                detail_root = ET.fromstring(detail_res.text)
                detail_db = detail_root.find("db")
            except Exception as e:
                print(f"  상세 API 호출 실패 ({type(e).__name__}): {e}")
                continue

            if detail_db is None:
                print(f"  상세 데이터 없음, 건너뜀: {prfnm}")
                continue

            sty = detail_db.findtext("sty")

            # ✅ [보완 1] 시설 API 호출 에러 처리 추가
            mt10id = detail_db.findtext("mt10id")
            adres, la, lo = None, None, None

            if mt10id:
                try:
                    facility_res = requests.get(
                        f"http://www.kopis.or.kr/openApi/restful/prfplc/{mt10id}",
                        params={"service": SERVICE_KEY},
                        timeout=10
                    )
                    facility_res.raise_for_status()
                    time.sleep(0.3)
                    facility_root = ET.fromstring(facility_res.text)
                    facility_db = facility_root.find("db")

                    if facility_db is not None:
                        adres = facility_db.findtext("adres")
                        la    = facility_db.findtext("la")
                        lo    = facility_db.findtext("lo")
                except Exception as e:
                    # ✅ [보완 3] 시설 API 실패 시 주소 없이 계속 진행
                    print(f"  시설 API 호출 실패 ({type(e).__name__}): {e}, 주소 없이 수집 계속")

            event_data = {
                "공연ID":    mt20id,
                "공연명":    detail_db.findtext("prfnm"),
                "공연시작일": detail_db.findtext("prfpdfrom"),
                "공연종료일": detail_db.findtext("prfpdto"),
                "공연장":    detail_db.findtext("fcltynm"),
                "장르":      detail_db.findtext("genrenm"),
                "공연상태":  detail_db.findtext("prfstate"),
                "관람연령":  detail_db.findtext("prfage"),
                "티켓가격":  detail_db.findtext("pcseguidance"),
                "포스터":    detail_db.findtext("poster"),
                "줄거리":    sty,
                "예매처":    detail_db.findtext("relatenm"),
                "예매링크":  detail_db.findtext("relateurl"),
                "주소":      adres,
                "위도":      la,
                "경도":      lo
            }
            results.append(event_data)
            time.sleep(0.5)

        page += 1

    df = pd.DataFrame(results)
    df.to_csv("kopis_raw.csv", index=False, encoding="utf-8-sig")
    print(f"✅ KOPIS 수집 완료: kopis_raw.csv ({len(df)}건 저장됨)")

    print(f"\n--- 줄거리 수집 현황 ---")
    print(f"줄거리 있음: {df['줄거리'].notna().sum()}건")
    print(f"줄거리 없음: {df['줄거리'].isna().sum()}건")


if __name__ == "__main__":
    fetch_kopis_events_test()