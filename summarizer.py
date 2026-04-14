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

# 신규 출시 관련 키워드 (제목에 하나라도 포함되면 1차 통과)
RELEASE_KEYWORDS = [
    "정식 출시", "정식출시", "정식 발매", "정식발매",
    "사전예약", "사전 예약", "사전다운로드", "사전 다운로드",
    "얼리 액세스", "앞서 해보기",
    "신작", "신규 게임",
    "메타크리틱", "오픈크리틱",
    "출시 예정", "발매 예정", "출시일",
    "28일 출시", "일 출시", "일 발매", "일 런칭", "일 오픈",
]

# 제목에 있으면 무조건 제외 (과거 사건, 주년 기념 등)
EXCLUDE_KEYWORDS = [
    "주년", "기념", "유출", "해킹", "폐서", "서비스 종료",
    "업데이트", "패치", "이벤트", "콜라보", "논란", "사건",
    "인터뷰", "근황", "소식통", "루머", "추측",
]

_model = None
MAX_RETRIES = 2
RETRY_DELAY = 15


def _keyword_match(title: str, content: str) -> bool:
    """제목 기준으로 신규 출시 관련 기사인지 판단합니다."""
    title_lower = title.lower()

    # 제외 키워드가 제목에 있으면 탈락
    if any(kw in title_lower for kw in EXCLUDE_KEYWORDS):
        return False

    # 출시 키워드가 제목에 있으면 통과
    if any(kw.lower() in title_lower for kw in RELEASE_KEYWORDS):
        return True

    # 본문 앞부분 보조 확인 (제목에 없을 때만)
    body_preview = content[:200].lower()
    strong_keywords = ["정식 출시", "정식출시", "사전예약", "출시 예정", "발매 예정"]
    return any(kw in body_preview for kw in strong_keywords)


def _get_model():
    global _model
    if _model is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        genai.configure(api_key=api_key)
        # 사용 가능한 모델 목록 조회
        try:
            available = [
                m.name.replace("models/", "")
                for m in genai.list_models()
                if "generateContent" in [s.name for s in m.supported_generation_methods]
            ]
            logger.info(f"사용 가능한 Gemini 모델: {available}")
        except Exception as e:
            logger.warning(f"모델 목록 조회 실패: {e}")
            available = []

        # 우선순위대로 모델 선택
        preferred = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        selected = next((m for m in preferred if m in available), None)

        if not selected and available:
            selected = available[0]

        if not selected:
            raise RuntimeError("사용 가능한 Gemini 모델이 없습니다. API 키를 확인해 주세요.")

        _model = genai.GenerativeModel(selected)
        logger.info(f"선택된 Gemini 모델: {selected}")
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
