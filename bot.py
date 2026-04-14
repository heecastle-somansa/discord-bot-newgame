"""
메인 진입점. GitHub Actions에서 python bot.py 로 실행됩니다.
"""

import json
import logging
import sys
import time
from pathlib import Path

from crawlers import CRAWLER_REGISTRY, Post
from discord_poster import build_embed, post_to_discord
from summarizer import batch_filter_and_summarize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

SOURCES_FILE = Path("config/sources.json")
SEEN_FILE = Path("seen_posts.json")


def load_sources() -> list[dict]:
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return [s for s in data["sources"] if s.get("enabled", True)]


def load_seen() -> dict[str, list[str]]:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            pass
    return {}


def save_seen(seen: dict[str, list[str]]) -> None:
    SEEN_FILE.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run() -> None:
    logger.info("=" * 60)
    logger.info("뉴스봇 실행 시작")

    sources = load_sources()
    seen = load_seen()
    all_embeds: list[dict] = []
    updated_seen = {k: list(v) for k, v in seen.items()}

    for source in sources:
        source_id = source["id"]
        crawler_type = source.get("crawler_type", "")
        crawler_cls = CRAWLER_REGISTRY.get(crawler_type)

        if not crawler_cls:
            logger.warning(f"[{source_id}] 알 수 없는 crawler_type: '{crawler_type}' — 건너뜁니다.")
            continue

        logger.info(f"[{source_id}] 크롤링 시작: {source['url']}")

        crawler = crawler_cls(source)
        posts = crawler.fetch_post_list()

        seen_ids: set[str] = set(updated_seen.get(source_id, []))
        max_per_run: int = source.get("max_posts_per_run", 5)
        new_posts = [p for p in posts if p.id not in seen_ids][:max_per_run]

        if not new_posts:
            logger.info(f"[{source_id}] 신규 게시물 없음")
            continue

        logger.info(f"[{source_id}] 신규 게시물 {len(new_posts)}개 → Gemini 일괄 처리")

        # 본문이 없는 경우 개별 페이지에서 보완
        for post in new_posts:
            if not post.content:
                post.content = crawler.fetch_post_content(post.url)

        # Gemini 한 번 호출로 전체 필터링 + 요약
        summaries = batch_filter_and_summarize(new_posts, source)

        for post in new_posts:
            seen_ids.add(post.id)
            summary = summaries.get(post.id)
            if summary is None:
                continue
            embed = build_embed(post, summary, source)
            all_embeds.append(embed)

        updated_seen[source_id] = list(seen_ids)

    if not all_embeds:
        logger.info("전송할 신규 게시물 없음 — 종료")
        save_seen(updated_seen)
        return

    logger.info(f"Discord 전송 시작: 총 {len(all_embeds)}개 embed")
    success = post_to_discord(all_embeds)

    if success:
        save_seen(updated_seen)
        logger.info("seen_posts.json 저장 완료")
    else:
        logger.error("Discord 전송 실패 — seen_posts.json 저장 안 함 (다음 실행 시 재시도)")

    logger.info("뉴스봇 실행 종료")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
