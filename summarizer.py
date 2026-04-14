"""
신규 게임 출시 기사 필터링 + Gemini AI 요약

처리 흐름:
  1. 키워드 필터 (무료, API 불필요) → 관련 없는 기사 대부분 제거
  2. Gemini 요약 (키워드 통과 기사만, 보통 1~3개)
"""

import logging
import os
import re
import time

import google.generativeai as genai

from crawlers.base import Post

logger = logging.getLogger(__name__)

# 신규 출시 관련 키워드 (제목에 하나라도 포함되면 통과)
RELEASE_KEYWORDS = [
    "출시", "발매", "런칭", "오픈", "정식 서비스", "정식서비스",
    "사전예약", "사전 예약", "사전다운로드", "사전 다운로드",
    "얼리 액세스", "앞서 해보기",
    "신작", "신규 게임", "새 게임",
    "리뷰", "평점", "메타크리틱", "오픈크리틱",
    "released", "launch", "release date",
]

_model = None
MAX_RETRIES = 2
RETRY_DELAY = 15


def _keyword_match(title: str, content: str) -> bool:
    """제목 또는 본문 앞부분에 출시 관련 키워드가 있는지 확인합니다."""
    text = (title + " " + content[:300]).lower()
    return any(kw.lower() in text for kw in RELEASE_KEYWORDS)


def _get_model():
    global _model
    if _model is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        genai.configure(api_key=api_key)
        # 모델 우선순위: 2.0-flash → 1.5-flash → pro 순으로 시도
        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]:
            try:
                m = genai.GenerativeModel(model_name)
                m.generate_content("test", generation_config={"max_output_tokens": 1})
                _model = m
                logger.info(f"Gemini 모델 사용: {model_name}")
                break
            except Exception:
                continue
        if _model is None:
            raise RuntimeError("사용 가능한 Gemini 모델이 없습니다.")
    return _model


def _call_gemini(prompt: str) -> str:
    for attempt in range(MAX_RETRIES):
        try:
            response = _get_model().generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "exhausted" in err.lower():
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Gemini 한도 — {wait}초 후 재시도 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                logger.error(f"Gemini 오류: {e}")
                return ""
    logger.error("Gemini 재시도 초과 — 키워드 기반 요약으로 대체")
    return ""


def _fallback_summary(post: Post) -> str:
    """Gemini 실패 시 본문 앞부분을 그대로 사용합니다."""
    content = post.content[:300].strip() if post.content else ""
    return content or "(요약 없음 — 원문 링크를 확인해 주세요)"


def filter_and_summarize(post: Post, source: dict) -> str | None:
    """
    단일 기사를 필터링하고 요약합니다.
    - 키워드 미해당 → None 반환 (건너뜀)
    - 키워드 해당 → Gemini 요약문 반환
    """
    if not _keyword_match(post.title, post.content):
        logger.info(f"[키워드 제외] {post.title[:50]}")
        return None

    logger.info(f"[키워드 통과] {post.title[:50]}")

    body = post.content[:1500] if post.content else "(본문 없음)"
    prompt = f"""다음 게임 뉴스 기사를 요약해 주세요.

제목: {post.title}
본문: {body}

아래 형식으로 작성하세요 (이모지 금지, ~습니다 체):
게임명: (게임 이름)
플랫폼: (PC / 모바일 / 콘솔 / 멀티플랫폼)
출시일: (출시일 또는 예정일, 모르면 미정)
요약: (핵심 내용 2~3줄)"""

    result = _call_gemini(prompt)
    if not result:
        return _fallback_summary(post)

    return result
