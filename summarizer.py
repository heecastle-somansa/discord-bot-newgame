"""
Gemini AI로 게임 뉴스 기사를 필터링하고 요약합니다.

filter_and_summarize() 가 반환하는 값:
  - None  → 신규 게임 출시/발매와 관련 없는 기사 (Discord에 올리지 않음)
  - str   → 요약 텍스트 (Discord에 포스팅)
"""

import logging
import os

import google.generativeai as genai

from crawlers.base import Post

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("gemini-2.0-flash")
    return _model


def filter_and_summarize(post: Post, source: dict) -> str | None:
    """
    기사가 '신규 게임 출시·발매 소식'에 해당하면 요약문을 반환합니다.
    해당하지 않으면 None을 반환합니다.
    """
    body = post.content.strip() if post.content.strip() else "(본문 없음)"

    prompt = f"""다음은 게임 뉴스 기사입니다. 두 가지 작업을 순서대로 수행해 주세요.

[기사 제목]
{post.title}

[기사 본문]
{body[:2000]}

---

작업 1 - 분류:
이 기사가 아래 중 하나에 해당하면 "YES", 해당하지 않으면 "NO"로만 답하세요.
- 신규 게임의 출시, 발매, 런칭 소식
- 신규 게임의 출시 일정 공개
- 신규 게임의 사전 예약·사전 다운로드 시작
- 신규 게임의 출시 후 리뷰·평점 공개

작업 2 - 요약 (작업 1이 YES인 경우에만):
아래 형식으로 정확히 작성하세요.

RESULT: YES
게임명: (게임 이름)
플랫폼: (PC / 모바일 / 콘솔 / 멀티플랫폼 중 해당)
출시일: (출시일 또는 예정일, 모르면 "미정")
요약: (핵심 내용 2~3줄. ~습니다 체. 이모지 금지.)

작업 1이 NO인 경우:
RESULT: NO"""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        text = response.text.strip()

        if "RESULT: NO" in text or not text.startswith("RESULT: YES"):
            logger.info(f"[필터 제외] {post.title[:40]}")
            return None

        # "RESULT: YES\n" 이후 내용만 추출
        summary = text.replace("RESULT: YES", "").strip()
        logger.info(f"[필터 통과] {post.title[:40]}")
        return summary

    except Exception as e:
        logger.error(f"Gemini 오류 (post_id={post.id}): {e}")
        return None
