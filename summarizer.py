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


def summarize(post: Post, source: dict) -> str:
    """게시글을 Gemini AI로 요약합니다. 실패 시 빈 문자열 반환."""
    source_name = source.get("name", "")
    body = post.content.strip() if post.content.strip() else "(본문 없음 - 제목만으로 요약)"

    prompt = f"""다음 뉴스 기사를 한국어로 요약해 주세요.

출처: {source_name}
카테고리: {post.category or "일반"}
제목: {post.title}
본문:
{body}

요약 규칙:
- 핵심 내용만 3~5줄로 작성
- 독자가 원문 없이도 내용을 파악할 수 있도록 작성
- 광고, 관련기사 링크 등 불필요한 내용 제외
- 이모지 사용 금지
- 문장은 ~습니다 체로 마무리"""

    try:
        model = _get_model()
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini 요약 실패 (post_id={post.id}): {e}")
        return ""
