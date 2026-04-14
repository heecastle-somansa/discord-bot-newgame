import logging
import re

from bs4 import BeautifulSoup

from .base import BaseCrawler, Post

logger = logging.getLogger(__name__)


class QuasarzoneCrawler(BaseCrawler):
    """퀘이사존 게시판 크롤러. crawler_type: "quasarzone" """

    MAX_CONTENT_LENGTH = 3000

    def fetch_post_list(self) -> list[Post]:
        url = self.config["url"]
        response = self._get(url)
        if not response:
            logger.error(f"[{self.config['id']}] 목록 페이지 요청 실패: {url}")
            return []

        soup = BeautifulSoup(response.text, "lxml")
        posts: list[Post] = []

        for row in soup.select("ul.list-board-wrap li.relative"):
            title_tag = row.select_one("p.subject a")
            if not title_tag:
                continue

            href = title_tag.get("href", "")
            if not href or "/views/" not in href:
                continue

            post_id = href.rstrip("/").split("/")[-1]
            title = title_tag.get_text(strip=True)
            full_url = (
                f"https://quasarzone.com{href}" if href.startswith("/") else href
            )

            category_tag = row.select_one("span.category-item")
            category = category_tag.get_text(strip=True) if category_tag else ""

            comment_tag = row.select_one("span.ctn-count")
            comment_count = comment_tag.get_text(strip=True) if comment_tag else "0"

            posts.append(
                Post(
                    id=post_id,
                    title=title,
                    url=full_url,
                    category=category,
                    comment_count=comment_count,
                )
            )

        logger.info(f"[{self.config['id']}] 목록 {len(posts)}개 수집")
        return posts

    def fetch_post_content(self, url: str) -> str:
        response = self._get(url)
        if not response:
            return ""

        soup = BeautifulSoup(response.text, "lxml")

        content_tag = (
            soup.select_one("div.view-content")
            or soup.select_one("div.article-body")
            or soup.select_one("div#article-content")
        )
        if not content_tag:
            return ""

        for tag in content_tag.select("script, style, iframe"):
            tag.decompose()

        text = content_tag.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[: self.MAX_CONTENT_LENGTH]
