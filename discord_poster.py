"""
Discord Webhook으로 embed 메시지를 전송합니다.

공통 embed 양식:
┌──────────────────────────────────────────────┐
│ [소스 아이콘] 소스 이름          ← author    │
│                                              │
│ 게시글 제목 (클릭 시 원문 이동)  ← title     │
│                                              │
│ AI 요약 내용 3~5줄...           ← description│
│                                              │
│ 카테고리: PC게임  │  댓글: 13개  ← fields    │
│                                              │
│ 소스이름 · 2026-04-14 14:00     ← footer     │
└──────────────────────────────────────────────┘
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests

from crawlers.base import Post

logger = logging.getLogger(__name__)

DISCORD_CHUNK_SIZE = 10


def build_embed(post: Post, summary: str, source: dict) -> dict:
    """공통 양식의 Discord embed 딕셔너리를 생성합니다."""
    category = post.category or "일반"
    comment_count = post.comment_count or "0"
    source_name = source.get("name", "뉴스봇")
    source_icon = source.get("icon", "📌")
    color = source.get("color", 0x5865F2)

    description = summary if summary else "_(요약을 가져오지 못했습니다. 원문을 확인해 주세요.)_"

    now_kst = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return {
        "author": {
            "name": f"{source_icon}  {source_name}",
            "url": source.get("url", ""),
        },
        "title": post.title,
        "url": post.url,
        "description": description,
        "color": color,
        "fields": [
            {
                "name": "카테고리",
                "value": category,
                "inline": True,
            },
            {
                "name": "댓글",
                "value": f"{comment_count}개",
                "inline": True,
            },
        ],
        "footer": {
            "text": f"{source_name}  ·  {now_kst}",
        },
    }


def post_to_discord(embeds: list[dict]) -> bool:
    """Discord Webhook으로 embed 목록을 전송합니다."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
        return False

    success = True
    for i in range(0, len(embeds), DISCORD_CHUNK_SIZE):
        chunk = embeds[i : i + DISCORD_CHUNK_SIZE]
        payload = {
            "username": "뉴스봇",
            "embeds": chunk,
        }
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if response.status_code in (200, 204):
                logger.info(f"Discord 전송 성공: {len(chunk)}개 embed")
            else:
                logger.error(
                    f"Discord 전송 실패: HTTP {response.status_code} / {response.text[:200]}"
                )
                success = False
        except requests.RequestException as e:
            logger.error(f"Discord 요청 오류: {e}")
            success = False

        time.sleep(1)

    return success
