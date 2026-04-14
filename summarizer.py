"""
Gemini AI로 게임 뉴스 기사를 필터링하고 요약합니다.

핵심 설계:
- 기사 여러 개를 한 번의 API 호출로 처리 (rate limit 방지)
- "신규 게임 출시/발매" 관련 기사만 Discord에 전송
- 해당하지 않으면 None 반환
"""

import json
import logging
import os
import time

import google.generativeai as genai

from crawlers.base import Post

logger = logging.getLogger(__name__)

_model = None
MAX_RETRIES = 3
RETRY_DELAY = 10  # 초


def _get_model():
    global _model
    if _model is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("gemini-2.0-flash")
    return _model


def _call_gemini(prompt: str) -> str:
    """재시도 로직 포함 Gemini 호출."""
    model = _get_model()
    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Gemini 한도 초과 — {wait}초 후 재시도 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                logger.error(f"Gemini 오류: {e}")
                return ""
    logger.error("Gemini 최대 재시도 횟수 초과")
    return ""


def batch_filter_and_summarize(posts: list[Post], source: dict) -> dict[str, str | None]:
    """
    여러 기사를 한 번의 Gemini 호출로 필터링 + 요약합니다.

    반환값: { post.id: 요약문 또는 None }
      - 요약문  → 신규 게임 출시 관련 기사 (Discord 전송 대상)
      - None    → 관련 없는 기사 (건너뜀)
    """
    if not posts:
        return {}

    articles_text = ""
    for i, post in enumerate(posts):
        body = post.content[:800] if post.content else "(본문 없음)"
        articles_text += f"""
--- 기사 {i+1} (ID: {post.id}) ---
제목: {post.title}
본문: {body}
"""

    prompt = f"""다음은 게임 뉴스 기사 목록입니다.
각 기사에 대해 두 가지를 판단하고, 아래 JSON 형식으로만 응답하세요.

판단 기준 - 아래 중 하나에 해당하면 RELEVANT:
- 신규 게임의 출시, 발매, 런칭 소식
- 신규 게임의 출시 일정 공개
- 신규 게임의 사전 예약·사전 다운로드 시작
- 신규 게임의 출시 후 첫 리뷰·평점 공개

{articles_text}

응답 형식 (JSON 배열, 다른 텍스트 없이 JSON만):
[
  {{
    "id": "기사ID",
    "relevant": true 또는 false,
    "game_name": "게임명 (relevant=true일 때만)",
    "platform": "PC/모바일/콘솔/멀티플랫폼 (relevant=true일 때만)",
    "release_date": "출시일 또는 예정일, 모르면 미정 (relevant=true일 때만)",
    "summary": "핵심 내용 2~3줄 요약. ~습니다 체. (relevant=true일 때만)"
  }}
]"""

    raw = _call_gemini(prompt)
    if not raw:
        return {post.id: None for post in posts}

    # JSON 파싱
    try:
        # 코드블록 제거
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Gemini 응답 JSON 파싱 실패: {e}\n응답: {raw[:300]}")
        return {post.id: None for post in posts}

    result: dict[str, str | None] = {post.id: None for post in posts}

    for item in items:
        pid = str(item.get("id", ""))
        if not item.get("relevant"):
            logger.info(f"[필터 제외] id={pid}")
            continue

        summary_lines = [
            f"**게임명:** {item.get('game_name', '-')}",
            f"**플랫폼:** {item.get('platform', '-')}  |  **출시일:** {item.get('release_date', '미정')}",
            f"{item.get('summary', '')}",
        ]
        result[pid] = "\n".join(summary_lines)
        logger.info(f"[필터 통과] id={pid} | {item.get('game_name', '')}")

    return result
