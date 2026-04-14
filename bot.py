"""
신규 게임 출시 뉴스봇 — 메인 진입점
GitHub Actions 에서 `python bot.py` 로 실행됩니다.

실행 흐름:
  1. config/sources.json 에서 활성화된 소스 목록 로드
  2. 각 소스별로 RSS 피드 수집
  3. 이전에 처리한 기사(seen_posts.json) 제외 → 신규 기사만 선별
  4. 키워드 필터 → Gemini AI 요약
  5. Discord Webhook 으로 embed 전송
  6. 처리된 기사 ID를 seen_posts.json 에 저장 (중복 방지)
"""

import json
import logging
import sys
import time
from pathlib import Path

from crawlers import CRAWLER_REGISTRY
from discord_poster import build_embed, post_to_discord
from summarizer import filter_and_summarize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

SOURCES_FILE = Path("config/sources.json")
SEEN_FILE = Path("seen_posts.json")


def load_sources() -> list[dict]:
    """sources.json 에서 enabled=true 인 소스만 반환합니다."""
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return [s for s in data["sources"] if s.get("enabled", True)]


def load_seen() -> dict[str, list[str]]:
    """seen_posts.json 을 로드합니다. 파일이 없으면 빈 딕셔너리를 반환합니다."""
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            pass
    return {}


def save_seen(seen: dict[str, list[str]]) -> None:
    """처리된 기사 ID 목록을 seen_posts.json 에 저장합니다."""
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
        crawler_cls = CRAWLER_REGISTRY.get(source.get("crawler_type", ""))

        if not crawler_cls:
            logger.warning(f"[{source_id}] 알 수 없는 crawler_type — 건너뜁니다.")
            continue

        logger.info(f"[{source_id}] 수집 시작: {source['url']}")

        crawler = crawler_cls(source)
        posts = crawler.fetch_post_list()

        # 이미 처리한 기사 제외
        seen_ids: set[str] = set(updated_seen.get(source_id, []))
        max_per_run: int = source.get("max_posts_per_run", 10)
        new_posts = [p for p in posts if p.id not in seen_ids][:max_per_run]

        if not new_posts:
            logger.info(f"[{source_id}] 신규 기사 없음")
            continue

        logger.info(f"[{source_id}] 신규 기사 {len(new_posts)}개 → 필터링 및 요약")

        for post in new_posts:
            # RSS 크롤러는 fetch_post_content 가 "" 를 반환하므로 본문은 이미 post.content 에 있음
            if not post.content:
                post.content = crawler.fetch_post_content(post.url)

            summary = filter_and_summarize(post, source)
            seen_ids.add(post.id)  # 필터 제외 기사도 다음 실행에서 재처리하지 않음

            if summary is None:
                continue

            all_embeds.append(build_embed(post, summary, source))
            time.sleep(1)

        updated_seen[source_id] = list(seen_ids)

    if not all_embeds:
        logger.info("전송할 기사 없음 — 종료")
        save_seen(updated_seen)
        return

    logger.info(f"Discord 전송 시작: 총 {len(all_embeds)}개")
    success = post_to_discord(all_embeds)

    if success:
        save_seen(updated_seen)
        logger.info("seen_posts.json 저장 완료")
    else:
        # 전송 실패 시 seen 저장 안 함 → 다음 실행 때 재시도
        logger.error("Discord 전송 실패 — 다음 실행 시 재시도됩니다.")

    logger.info("뉴스봇 실행 종료")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
