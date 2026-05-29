from __future__ import annotations

import importlib.util
import logging
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
RECOMMENDATION_PATH = BASE_DIR / "2_recommendation.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("arbit.recommendations")


def _load_recommendation_module():
    spec = importlib.util.spec_from_file_location("recommendation", RECOMMENDATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"추천 모듈을 불러올 수 없습니다: {RECOMMENDATION_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recommendation = _load_recommendation_module()


app = FastAPI(
    title="서울 문화행사 추천 API",
    description="서울 문화행사 데이터를 불러와 사용자가 선택한 관심 행사 기반으로 맞춤 추천을 제공하는 API입니다.",
    version="1.0.0",
)


@app.middleware("http")
async def log_recommendations_http(request: Request, call_next):
    if request.url.path != "/recommendations":
        return await call_next(request)

    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started_at = time.perf_counter()
    client_host = request.client.host if request.client else "-"

    logger.info(
        "request.start request_id=%s method=%s path=%s client=%s",
        request_id,
        request.method,
        request.url.path,
        client_host,
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.exception(
            "request.error request_id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request.end request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


class RecommendationRequest(BaseModel):
    event_ids: list[int] = Field(
        ...,
        min_length=4,
        max_length=5,
        description="취향 프로필을 만들기 위해 사용자가 관심 행사로 선택한 event_id 4~5개입니다.",
        examples=[[0, 12, 34, 56]],
    )
    limit: int = Field(10, ge=1, le=50, description="추천 결과로 반환할 최대 행사 개수입니다.")


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _row_to_event(row: pd.Series, include_scores: bool = False) -> dict[str, Any]:
    event = {
        "event_id": int(row["event_id"]),
        "title": _clean_value(row["title"]),
        "genre": _clean_value(row["genre"]),
        "district": _clean_value(row["district"]),
        "is_free": bool(row["is_free"]),
        "start_date": str(row["start_date"]),
        "end_date": str(row["end_date"]),
        "description": _clean_value(row.get("description")),
        "age_label": _clean_value(row["age_label"]),
        "mood_tags": list(row["mood_tags"]) if isinstance(row["mood_tags"], list) else [],
        "mood_source": _clean_value(row.get("mood_source")),
        "status": _clean_value(row.get("status")),
        "days_left": int(row["days_left"]) if "days_left" in row and not pd.isna(row["days_left"]) else None,
    }

    if include_scores:
        event.update(
            {
                "score": float(row["score"]),
                "match_pct": float(row["match_pct"]),
                "genre_score": float(row["genre_score"]),
                "mood_score": float(row["mood_score"]),
                "urgency": float(row["urgency"]),
            }
        )

    return event


@lru_cache(maxsize=1)
def get_events_df() -> pd.DataFrame:
    try:
        return recommendation.load_data()
    except FileNotFoundError as exc:
        raise RuntimeError(
            "events_with_mood.csv 파일이 없습니다. 1_llm_mood_extractor.py를 먼저 실행하세요."
        ) from exc


@app.get(
    "/health",
    summary="서버 상태 확인",
    description="추천 API 서버가 정상 작동 중인지와 현재 로드된 행사 데이터 개수를 확인합니다.",
)
def health() -> dict[str, Any]:
    df = get_events_df()
    return {
        "status": "ok",
        "events_count": len(df),
        "data_file": recommendation.INPUT_CSV,
    }


@app.post(
    "/reload",
    summary="행사 데이터 새로고침",
    description="캐시에 저장된 행사 데이터를 비우고 CSV 파일을 다시 읽어 최신 데이터로 갱신합니다.",
)
def reload_data() -> dict[str, Any]:
    get_events_df.cache_clear()
    df = get_events_df()
    return {"status": "reloaded", "events_count": len(df)}


@app.get(
    "/events",
    summary="행사 목록 조회",
    description="전체 문화행사 목록을 페이지네이션으로 조회하고 장르, 자치구, 무료 여부로 필터링합니다.",
)
def list_events(
    limit: int = Query(20, ge=1, le=100, description="한 번에 조회할 행사 목록의 최대 개수입니다."),
    offset: int = Query(0, ge=0, description="목록 조회를 시작할 위치를 지정하는 페이지네이션 기준값입니다."),
    genre: str | None = Query(None, description="특정 장르의 행사만 조회하기 위한 필터입니다."),
    district: str | None = Query(None, description="특정 자치구의 행사만 조회하기 위한 필터입니다."),
    is_free: bool | None = Query(None, description="무료 행사 또는 유료 행사만 조회하기 위한 필터입니다."),
) -> dict[str, Any]:
    df = get_events_df()

    if genre:
        df = df[df["genre"] == genre]
    if district:
        df = df[df["district"] == district]
    if is_free is not None:
        df = df[df["is_free"] == is_free]

    total = len(df)
    page = df.iloc[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [_row_to_event(row) for _, row in page.iterrows()],
    }


@app.get(
    "/seed-events",
    summary="추천용 관심 행사 샘플 조회",
    description="사용자가 취향을 고를 수 있도록 랜덤 문화행사 샘플을 반환합니다.",
)
def seed_events(
    sample_size: int = Query(10, ge=4, le=50, description="사용자가 취향 선택을 할 수 있도록 랜덤으로 보여줄 행사 개수입니다."),
    random_state: int | None = Query(None, description="같은 랜덤 행사 샘플을 다시 보고 싶을 때 사용하는 시드 값입니다."),
) -> dict[str, Any]:
    df = get_events_df()
    sample = df.sample(n=min(sample_size, len(df)), random_state=random_state).reset_index(drop=True)
    return {
        "sample_size": len(sample),
        "message": "이 목록에서 관심 있는 event_id 4~5개를 POST /recommendations로 보내세요.",
        "events": [_row_to_event(row) for _, row in sample.iterrows()],
    }


@app.post(
    "/recommendations",
    summary="맞춤 행사 추천",
    description="사용자가 선택한 관심 행사 4~5개를 기반으로 취향 프로필을 만들고 추천 행사를 반환합니다.",
)
def recommend(payload: RecommendationRequest, request: Request) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", "-")
    logger.info(
        "recommendations.payload request_id=%s event_ids=%s limit=%s",
        request_id,
        payload.event_ids,
        payload.limit,
    )

    df = get_events_df()
    logger.info(
        "recommendations.data_loaded request_id=%s events_count=%s",
        request_id,
        len(df),
    )

    event_ids = list(dict.fromkeys(payload.event_ids))

    if len(event_ids) != len(payload.event_ids):
        logger.warning(
            "recommendations.validation_failed request_id=%s reason=duplicate_event_ids event_ids=%s",
            request_id,
            payload.event_ids,
        )
        raise HTTPException(status_code=400, detail="event_ids에 중복 값이 있습니다.")

    selected_df = df[df["event_id"].isin(event_ids)].copy()
    missing_ids = sorted(set(event_ids) - set(selected_df["event_id"].tolist()))
    if missing_ids:
        logger.warning(
            "recommendations.validation_failed request_id=%s reason=missing_event_ids missing_event_ids=%s",
            request_id,
            missing_ids,
        )
        raise HTTPException(status_code=404, detail={"missing_event_ids": missing_ids})

    selected_df["_request_order"] = selected_df["event_id"].apply(event_ids.index)
    selected_df = selected_df.sort_values("_request_order").drop(columns=["_request_order"]).reset_index(drop=True)
    logger.info(
        "recommendations.selected request_id=%s selected_count=%s selected_event_ids=%s",
        request_id,
        len(selected_df),
        selected_df["event_id"].tolist(),
    )

    genre_weights, mood_weights, allowed_ages = recommendation.extract_preference_profile(selected_df)
    logger.info(
        "recommendations.profile request_id=%s genre_weights=%s mood_weights=%s allowed_ages=%s",
        request_id,
        genre_weights,
        mood_weights,
        sorted(allowed_ages),
    )

    selected_ids = set(selected_df["event_id"].tolist())
    candidates = df[
        df["age_label"].isin(allowed_ages)
        & ~df["event_id"].isin(selected_ids)
    ].reset_index(drop=True)
    logger.info(
        "recommendations.candidates request_id=%s candidates_count=%s",
        request_id,
        len(candidates),
    )

    if candidates.empty:
        logger.info(
            "recommendations.response request_id=%s candidates_count=0 recommendations_count=0",
            request_id,
        )
        return {
            "selected_events": [_row_to_event(row) for _, row in selected_df.iterrows()],
            "preference_profile": {
                "genre_weights": genre_weights,
                "mood_weights": mood_weights,
                "allowed_ages": sorted(allowed_ages),
            },
            "candidates_count": 0,
            "recommendations": [],
        }

    scored = recommendation.score_all(candidates, genre_weights, mood_weights)
    scored = scored.head(payload.limit)
    logger.info(
        "recommendations.scored request_id=%s recommendations_count=%s top_event_ids=%s",
        request_id,
        len(scored),
        scored["event_id"].tolist(),
    )

    response = {
        "selected_events": [_row_to_event(row) for _, row in selected_df.iterrows()],
        "preference_profile": {
            "genre_weights": genre_weights,
            "mood_weights": mood_weights,
            "allowed_ages": sorted(allowed_ages),
        },
        "candidates_count": len(candidates),
        "recommendations": [_row_to_event(row, include_scores=True) for _, row in scored.iterrows()],
    }
    logger.info(
        "recommendations.response request_id=%s candidates_count=%s recommendations_count=%s",
        request_id,
        response["candidates_count"],
        len(response["recommendations"]),
    )
    return response
