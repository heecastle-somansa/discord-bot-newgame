"""
범용 RSS 크롤러. crawler_type: "rss"

RSS를 공식 제공하는 사이트는 Cloudflare 차단 없이 안정적으로 수집됩니다.
기사 본문이 RSS 피드에 포함되어 있으므로 별도 페이지 접속이 필요 없습니다.

sources.json 에서 "url" 에 RSS 피드 URL을 입력하면 됩니다.
"""

import hashlib
import logging
import re
from xml.etree import ElementTree as ET

from .base import BaseCrawler, Post

logger = logging.getLogger(__name__)

_NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom":    "http://www.w3.org/2005/Atom",
    "dc":      "http://purl.org/dc/elements/1.1/",
}


def _find_text(el, *paths: str) -> str:
    for path in paths:
        node = el.find(path, _NS)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


class RssCrawler(BaseCrawler):
    """범용 RSS 크롤러. crawler_type: "rss" """

    MAX_CONTENT = 3000

    def fetch_post_list(self) -> list[Post]:
        response = self._get(self.config["url"])
        if not response:
            logger.error(f"[{self.config['id']}] RSS 요청 실패: {self.config['url']}")
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            logger.error(f"[{self.config['id']}] RSS 파싱 실패: {e}")
            return []

        items = root.findall(".//item") or root.findall(".//atom:entry", _NS)
        posts: list[Post] = []

        for item in items:
            link = _find_text(item, "link", "guid")
            if not link or not link.startswith("http"):
                # Atom <link href="..."> 처리
                link_el = item.find("link")
                if link_el is not None:
                    link = link_el.get("href", "")
            if not link:
                continue

            title   = _find_text(item, "title")
            category = _find_text(item, "category", "dc:subject")

            # 기사 본문: content:encoded > description 순서로 추출
            raw_content = (
                _find_text(item, "content:encoded")
                or _find_text(item, "description")
            )
            content = _strip_html(raw_content)[: self.MAX_CONTENT]

            posts.append(Post(
                id=_make_id(link),
                title=title,
                url=link,
                category=category,
                content=content,
            ))

        logger.info(f"[{self.config['id']}] RSS {len(posts)}개 수집")
        return posts

    def fetch_post_content(self, url: str) -> str:
        # RSS에 이미 본문이 포함되어 있으므로 별도 요청 불필요
        return ""
