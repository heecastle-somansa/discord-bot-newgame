"""
신규 게임 출시 기사 필터링 + Gemini AI 요약

처리 흐름:
  1. 키워드 필터  — API 호출 없이 관련 없는 기사를 먼저 제거
  2. Gemini 요약  — 통과한 기사만 AI로 요약 (보통 1~3개/실행)

Gemini 무료 한도 (gemini-2.0-flash 기준):
  - 분당 15회 (RPM) / 하루 1,500회 (RPD)
  - 정상 운영(매 시간 자동 실행) 시 하루 최대 ~48회 호출로 여유 있음
"""

import logging
import os
import time

from google import genai

from crawlers.base import Post

logger = logging.getLogger(__name__)

# ── 키워드 필터 설정 ──────────────────────────────────────────
# 제목에 하나라도 포함되면 Gemini 요약 대상으로 분류
RELEASE_KEYWORDS = [
    "정식 출시", "정식출시", "정식 발매", "정식발매",
    "사전예약", "사전 예약", "사전다운로드", "사전 다운로드",
    "얼리 액세스", "앞서 해보기",
    "신작", "신규 게임",
    "메타크리틱", "오픈크리틱",
    "출시 예정", "발매 예정", "출시일",
    "일 출시", "일 발매", "일 런칭", "일 오픈",
]

# 제목에 하나라도 포함되면 무조건 제외 (주년 기념, 업데이트 등)
EXCLUDE_KEYWORDS = [
    "주년", "기념", "유출", "해킹", "서비스 종료",
    "업데이트", "패치", "이벤트", "콜라보", "논란",
    "인터뷰", "근황", "루머", "추측", "행사",
]

# ── Gemini 설정 ───────────────────────────────────────────────
# 우선순위 순서: 성능 좋은 모델부터 시도
PREFERRED_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]

MAX_RETRIES = 3
RETRY_DELAY = 60       # 429(한도 초과) 발생 시 재시도 전 대기 시간 (초)
INTER_REQUEST_DELAY = 5  # 기사 간 기본 대기 시간 — RPM 초과 방지

_client = None
_model_name = None


def _get_client():
    """Gemini 클라이언트를 초기화하고 사용 가능한 최적 모델을 선택합니다."""
    global _client, _model_name
    if _client is not None:
        return _client, _model_name

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

    _client = genai.Client(api_key=api_key)

    # 계정에서 실제로 사용 가능한 모델 목록 조회
    try:
        available = [
            m.name.replace("models/", "")
            for m in _client.models.list()
            if "generateContent" in (getattr(m, "supported_actions", None) or [])
        ]
        logger.info(f"사용 가능한 Gemini 모델: {available}")
        _model_name = next((m for m in PREFERRED_MODELS if m in available), None)
        if not _model_name and available:
            _model_name = available[0]
    except Exception as e:
        logger.warning(f"모델 목록 조회 실패: {e} — 기본값으로 대체")
        _model_name = PREFERRED_MODELS[0]

    logger.info(f"선택된 Gemini 모델: {_model_name}")
    return _client, _model_name


def _call_gemini(prompt: str) -> str:
    """Gemini API를 호출합니다. 한도 초과 시 최대 MAX_RETRIES 번 재시도합니다."""
    for attempt in range(MAX_RETRIES):
        try:
            client, model = _get_client()
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "exhausted" in err.lower():
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Gemini 한도 — {wait}초 후 재시도 ({attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                logger.error(f"Gemini 오류: {e}")
                return ""

    logger.error("Gemini 최대 재시도 초과")
    return ""


def _keyword_match(title: str, content: str) -> bool:
    """제목 기준으로 신규 게임 출시 관련 기사인지 판단합니다."""
    title_lower = title.lower()

    # 제외 키워드 먼저 확인
    if any(kw in title_lower for kw in EXCLUDE_KEYWORDS):
        return False

    # 출시 키워드가 제목에 있으면 통과
    if any(kw.lower() in title_lower for kw in RELEASE_KEYWORDS):
        return True

    # 제목에 없더라도 본문 앞부분에 강한 출시 키워드가 있으면 통과
    strong_keywords = ["정식 출시", "정식출시", "사전예약", "출시 예정", "발매 예정"]
    return any(kw in content[:200].lower() for kw in strong_keywords)


def filter_and_summarize(post: Post, source: dict) -> str | None:
    """
    기사를 필터링하고 요약합니다.
    - 신규 게임 출시 관련 → Gemini 요약문 반환
    - 관련 없음 → None 반환 (Discord에 올리지 않음)
    - Gemini 실패 → 본문 앞부분으로 대체 반환
    """
    if not _keyword_match(post.title, post.content):
        logger.info(f"[필터 제외] {post.title[:50]}")
        return None

    logger.info(f"[필터 통과] {post.title[:50]}")

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

    # Gemini 실패 시 본문 앞부분으로 대체
    if not result:
        logger.warning(f"Gemini 실패 — 본문으로 대체: {post.title[:40]}")
        return post.content[:300].strip() or "(요약 없음 — 원문 링크를 확인해 주세요)"

    return result
