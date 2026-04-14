"""
신규 게임 출시 기사 필터링 + Gemini AI 요약

처리 흐름:
  1. 키워드 필터 (무료, API 불필요) → 관련 없는 기사 대부분 제거
  2. Gemini 요약 (키워드 통과 기사만, 보통 1~3개)
"""

import logging
import os
import time

from google import genai

from crawlers.base import Post

logger = logging.getLogger(__name__)

# 신규 출시 관련 키워드 (제목에 하나라도 포함되면 통과)
RELEASE_KEYWORDS = [
    "정식 출시", "정식출시", "정식 발매", "정식발매",
    "사전예약", "사전 예약", "사전다운로드", "사전 다운로드",
    "얼리 액세스", "앞서 해보기",
    "신작", "신규 게임",
    "메타크리틱", "오픈크리틱",
    "출시 예정", "발매 예정", "출시일",
    "일 출시", "일 발매", "일 런칭", "일 오픈",
]

# 제목에 있으면 무조건 제외
EXCLUDE_KEYWORDS = [
    "주년", "기념", "유출", "해킹", "서비스 종료",
    "업데이트", "패치", "이벤트", "콜라보", "논란",
    "인터뷰", "근황", "루머", "추측", "행사",
]

_client = None
_model_name = None
MAX_RETRIES = 3
RETRY_DELAY = 60  # 429 발생 시 60초 대기
INTER_REQUEST_DELAY = 5  # 기사 간 기본 대기 (RPM 방지)

PREFERRED_MODELS = [
    "gemini-2.0-flash-lite",   # 무료 RPM 30 (가장 넉넉)
    "gemini-2.0-flash",        # 무료 RPM 15
    "gemini-1.5-flash-8b",     # 무료 RPM 15, 경량
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


def _get_client():
    global _client, _model_name
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        _client = genai.Client(api_key=api_key)

        # 사용 가능한 모델 탐색
        try:
            available = []
            for m in _client.models.list():
                name = m.name.replace("models/", "")
                actions = getattr(m, "supported_actions", []) or []
                if "generateContent" in actions:
                    available.append(name)
            logger.info(f"사용 가능한 Gemini 모델: {available}")
            _model_name = next((m for m in PREFERRED_MODELS if m in available), None)
            if not _model_name and available:
                _model_name = available[0]
        except Exception as e:
            logger.warning(f"모델 목록 조회 실패: {e} — 기본값 사용")
            _model_name = "gemini-2.0-flash"

        logger.info(f"선택된 Gemini 모델: {_model_name}")
    return _client, _model_name


def _call_gemini(prompt: str) -> str:
    for attempt in range(MAX_RETRIES):
        try:
            client, model = _get_client()
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
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
    logger.error("Gemini 재시도 초과")
    return ""


def _keyword_match(title: str, content: str) -> bool:
    title_lower = title.lower()
    if any(kw in title_lower for kw in EXCLUDE_KEYWORDS):
        return False
    if any(kw.lower() in title_lower for kw in RELEASE_KEYWORDS):
        return True
    body_preview = content[:200].lower()
    strong = ["정식 출시", "정식출시", "사전예약", "출시 예정", "발매 예정"]
    return any(kw in body_preview for kw in strong)


def _fallback_summary(post: Post) -> str:
    return post.content[:300].strip() if post.content else "(요약 없음 — 원문 링크를 확인해 주세요)"


def filter_and_summarize(post: Post, source: dict) -> str | None:
    """
    신규 게임 출시 관련 기사면 요약문 반환, 아니면 None.
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
플랫폼: (PC / 모바일 / 콘솔 / 멀티플랫폼 중 해당)
출시일: (출시일 또는 예정일, 모르면 미정)
요약: (핵심 내용 2~3줄)"""

    time.sleep(INTER_REQUEST_DELAY)
    result = _call_gemini(prompt)
    return result if result else _fallback_summary(post)
